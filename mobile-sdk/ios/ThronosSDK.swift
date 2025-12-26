/**
 * Thronos SDK for iOS
 * Native Swift implementation for iOS applications
 */

import Foundation
import Security

public class ThronosSDK {

    // MARK: - Properties

    private let apiUrl: String
    private let network: String
    private var currentWallet: Wallet?

    // MARK: - Initialization

    public init(apiUrl: String = "http://localhost:5000", network: String = "mainnet") {
        self.apiUrl = apiUrl
        self.network = network

        // Load wallet from keychain
        self.currentWallet = loadWalletFromKeychain()
    }

    // MARK: - Wallet Management

    /// Create a new wallet
    public func createWallet(completion: @escaping (Result<Wallet, Error>) -> Void) {
        guard let url = URL(string: "\(apiUrl)/api/wallet/create") else {
            completion(.failure(ThronosError.invalidURL))
            return
        }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        URLSession.shared.dataTask(with: request) { [weak self] data, response, error in
            if let error = error {
                completion(.failure(error))
                return
            }

            guard let data = data else {
                completion(.failure(ThronosError.noData))
                return
            }

            do {
                let wallet = try JSONDecoder().decode(Wallet.self, from: data)
                self?.currentWallet = wallet
                self?.saveWalletToKeychain(wallet)
                completion(.success(wallet))
            } catch {
                completion(.failure(error))
            }
        }.resume()
    }

    /// Import an existing wallet
    public func importWallet(address: String, secret: String) -> Result<Wallet, Error> {
        guard address.hasPrefix("THR") else {
            return .failure(ThronosError.invalidAddress)
        }

        let wallet = Wallet(address: address, secret: secret)
        self.currentWallet = wallet
        saveWalletToKeychain(wallet)

        return .success(wallet)
    }

    /// Get current wallet
    public func getWallet() -> Wallet? {
        return currentWallet
    }

    /// Check if wallet is connected
    public func isConnected() -> Bool {
        return currentWallet != nil
    }

    /// Disconnect wallet
    public func disconnect() {
        currentWallet = nil
        deleteWalletFromKeychain()
    }

    // MARK: - Token Operations

    /// Get token balances
    public func getBalances(address: String? = nil, showZero: Bool = false, completion: @escaping (Result<TokensResponse, Error>) -> Void) {
        let walletAddress = address ?? currentWallet?.address

        guard let walletAddress = walletAddress else {
            completion(.failure(ThronosError.noWallet))
            return
        }

        guard let url = URL(string: "\(apiUrl)/api/wallet/tokens/\(walletAddress)?show_zero=\(showZero)") else {
            completion(.failure(ThronosError.invalidURL))
            return
        }

        URLSession.shared.dataTask(with: url) { data, response, error in
            if let error = error {
                completion(.failure(error))
                return
            }

            guard let data = data else {
                completion(.failure(ThronosError.noData))
                return
            }

            do {
                let tokensResponse = try JSONDecoder().decode(TokensResponse.self, from: data)
                completion(.success(tokensResponse))
            } catch {
                completion(.failure(error))
            }
        }.resume()
    }

    /// Send transaction
    public func sendTransaction(to: String, amount: Double, token: String = "THR", completion: @escaping (Result<TransactionResponse, Error>) -> Void) {
        guard let wallet = currentWallet else {
            completion(.failure(ThronosError.noWallet))
            return
        }

        guard let url = URL(string: "\(apiUrl)/api/wallet/send") else {
            completion(.failure(ThronosError.invalidURL))
            return
        }

        let transaction = TransactionRequest(
            from: wallet.address,
            to: to,
            amount: amount,
            token: token,
            secret: wallet.secret
        )

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        do {
            request.httpBody = try JSONEncoder().encode(transaction)
        } catch {
            completion(.failure(error))
            return
        }

        URLSession.shared.dataTask(with: request) { data, response, error in
            if let error = error {
                completion(.failure(error))
                return
            }

            guard let data = data else {
                completion(.failure(ThronosError.noData))
                return
            }

            do {
                let txResponse = try JSONDecoder().decode(TransactionResponse.self, from: data)
                completion(.success(txResponse))
            } catch {
                completion(.failure(error))
            }
        }.resume()
    }

    // MARK: - Keychain Management

    private func saveWalletToKeychain(_ wallet: Wallet) {
        let addressData = wallet.address.data(using: .utf8)!
        let secretData = wallet.secret.data(using: .utf8)!

        // Save address
        let addressQuery: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrAccount as String: "thronos_wallet_address",
            kSecValueData as String: addressData
        ]

        SecItemDelete(addressQuery as CFDictionary)
        SecItemAdd(addressQuery as CFDictionary, nil)

        // Save secret
        let secretQuery: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrAccount as String: "thronos_wallet_secret",
            kSecValueData as String: secretData
        ]

        SecItemDelete(secretQuery as CFDictionary)
        SecItemAdd(secretQuery as CFDictionary, nil)
    }

    private func loadWalletFromKeychain() -> Wallet? {
        // Load address
        let addressQuery: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrAccount as String: "thronos_wallet_address",
            kSecReturnData as String: true
        ]

        var addressResult: AnyObject?
        let addressStatus = SecItemCopyMatching(addressQuery as CFDictionary, &addressResult)

        guard addressStatus == errSecSuccess,
              let addressData = addressResult as? Data,
              let address = String(data: addressData, encoding: .utf8) else {
            return nil
        }

        // Load secret
        let secretQuery: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrAccount as String: "thronos_wallet_secret",
            kSecReturnData as String: true
        ]

        var secretResult: AnyObject?
        let secretStatus = SecItemCopyMatching(secretQuery as CFDictionary, &secretResult)

        guard secretStatus == errSecSuccess,
              let secretData = secretResult as? Data,
              let secret = String(data: secretData, encoding: .utf8) else {
            return nil
        }

        return Wallet(address: address, secret: secret)
    }

    private func deleteWalletFromKeychain() {
        let addressQuery: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrAccount as String: "thronos_wallet_address"
        ]
        SecItemDelete(addressQuery as CFDictionary)

        let secretQuery: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrAccount as String: "thronos_wallet_secret"
        ]
        SecItemDelete(secretQuery as CFDictionary)
    }
}

// MARK: - Models

public struct Wallet: Codable {
    public let address: String
    public let secret: String
}

public struct Token: Codable {
    public let symbol: String
    public let name: String
    public let balance: Double
    public let decimals: Int
    public let color: String
    public let logo: String?
}

public struct TokensResponse: Codable {
    public let address: String
    public let tokens: [Token]
    public let last_updated: String
}

public struct TransactionRequest: Codable {
    public let from: String
    public let to: String
    public let amount: Double
    public let token: String
    public let secret: String
}

public struct TransactionResponse: Codable {
    public let success: Bool
    public let transaction: Transaction?
}

public struct Transaction: Codable {
    public let hash: String
    public let from: String
    public let to: String
    public let amount: Double
    public let token: String
    public let timestamp: String
}

// MARK: - Errors

public enum ThronosError: Error {
    case invalidURL
    case noData
    case noWallet
    case invalidAddress

    var localizedDescription: String {
        switch self {
        case .invalidURL:
            return "Invalid API URL"
        case .noData:
            return "No data received from server"
        case .noWallet:
            return "No wallet connected"
        case .invalidAddress:
            return "Invalid wallet address"
        }
    }
}
