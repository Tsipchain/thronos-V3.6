/**
 * Thronos SDK for Android
 * Native Kotlin implementation for Android applications
 */

package com.thronos.sdk

import android.content.Context
import android.content.SharedPreferences
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import com.google.gson.Gson
import com.google.gson.annotations.SerializedName
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.*
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.IOException

class ThronosSDK(
    private val context: Context,
    private val apiUrl: String = "http://localhost:5000",
    private val network: String = "mainnet"
) {

    private val gson = Gson()
    private val client = OkHttpClient()
    private var currentWallet: Wallet? = null
    private val preferences: SharedPreferences

    init {
        // Initialize encrypted shared preferences
        val masterKey = MasterKey.Builder(context)
            .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
            .build()

        preferences = EncryptedSharedPreferences.create(
            context,
            "thronos_wallet_prefs",
            masterKey,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
        )

        // Load wallet from storage
        currentWallet = loadWalletFromStorage()
    }

    // MARK: - Wallet Management

    /**
     * Create a new wallet
     */
    suspend fun createWallet(): Result<Wallet> = withContext(Dispatchers.IO) {
        try {
            val request = Request.Builder()
                .url("$apiUrl/api/wallet/create")
                .post("".toRequestBody("application/json".toMediaTypeOrNull()))
                .build()

            val response = client.newCall(request).execute()
            if (!response.isSuccessful) {
                return@withContext Result.failure(Exception("Failed to create wallet"))
            }

            val wallet = gson.fromJson(response.body?.string(), Wallet::class.java)
            currentWallet = wallet
            saveWalletToStorage(wallet)

            Result.success(wallet)
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    /**
     * Import an existing wallet
     */
    fun importWallet(address: String, secret: String): Result<Wallet> {
        if (!address.startsWith("THR")) {
            return Result.failure(Exception("Invalid address format"))
        }

        val wallet = Wallet(address, secret)
        currentWallet = wallet
        saveWalletToStorage(wallet)

        return Result.success(wallet)
    }

    /**
     * Get current wallet
     */
    fun getWallet(): Wallet? = currentWallet

    /**
     * Check if wallet is connected
     */
    fun isConnected(): Boolean = currentWallet != null

    /**
     * Disconnect wallet
     */
    fun disconnect() {
        currentWallet = null
        deleteWalletFromStorage()
    }

    // MARK: - Token Operations

    /**
     * Get token balances
     */
    suspend fun getBalances(
        address: String? = null,
        showZero: Boolean = false
    ): Result<TokensResponse> = withContext(Dispatchers.IO) {
        try {
            val walletAddress = address ?: currentWallet?.address
                ?: return@withContext Result.failure(Exception("No wallet connected"))

            val request = Request.Builder()
                .url("$apiUrl/api/wallet/tokens/$walletAddress?show_zero=$showZero")
                .get()
                .build()

            val response = client.newCall(request).execute()
            if (!response.isSuccessful) {
                return@withContext Result.failure(Exception("Failed to get balances"))
            }

            val tokensResponse = gson.fromJson(response.body?.string(), TokensResponse::class.java)
            Result.success(tokensResponse)
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    /**
     * Get balance for specific token
     */
    suspend fun getTokenBalance(tokenSymbol: String, address: String? = null): Result<Double> {
        val balancesResult = getBalances(address, true)
        return if (balancesResult.isSuccess) {
            val token = balancesResult.getOrNull()?.tokens?.find { it.symbol == tokenSymbol }
            Result.success(token?.balance ?: 0.0)
        } else {
            balancesResult.map { 0.0 }
        }
    }

    /**
     * Send transaction
     */
    suspend fun sendTransaction(
        to: String,
        amount: Double,
        token: String = "THR"
    ): Result<TransactionResponse> = withContext(Dispatchers.IO) {
        try {
            val wallet = currentWallet
                ?: return@withContext Result.failure(Exception("No wallet connected"))

            val transaction = TransactionRequest(
                from = wallet.address,
                to = to,
                amount = amount,
                token = token,
                secret = wallet.secret
            )

            val requestBody = gson.toJson(transaction)
                .toRequestBody("application/json".toMediaTypeOrNull())

            val request = Request.Builder()
                .url("$apiUrl/api/wallet/send")
                .post(requestBody)
                .build()

            val response = client.newCall(request).execute()
            if (!response.isSuccessful) {
                return@withContext Result.failure(Exception("Transaction failed"))
            }

            val txResponse = gson.fromJson(response.body?.string(), TransactionResponse::class.java)
            Result.success(txResponse)
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    /**
     * Get transaction history
     */
    suspend fun getTransactionHistory(
        address: String? = null,
        limit: Int = 50
    ): Result<List<Transaction>> = withContext(Dispatchers.IO) {
        try {
            val walletAddress = address ?: currentWallet?.address
                ?: return@withContext Result.failure(Exception("No wallet connected"))

            val request = Request.Builder()
                .url("$apiUrl/api/transactions/$walletAddress?limit=$limit")
                .get()
                .build()

            val response = client.newCall(request).execute()
            if (!response.isSuccessful) {
                return@withContext Result.failure(Exception("Failed to get transaction history"))
            }

            val transactions = gson.fromJson(response.body?.string(), Array<Transaction>::class.java).toList()
            Result.success(transactions)
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    // MARK: - Storage Management

    private fun saveWalletToStorage(wallet: Wallet) {
        preferences.edit().apply {
            putString("thronos_wallet_address", wallet.address)
            putString("thronos_wallet_secret", wallet.secret)
            apply()
        }
    }

    private fun loadWalletFromStorage(): Wallet? {
        val address = preferences.getString("thronos_wallet_address", null)
        val secret = preferences.getString("thronos_wallet_secret", null)

        return if (address != null && secret != null) {
            Wallet(address, secret)
        } else {
            null
        }
    }

    private fun deleteWalletFromStorage() {
        preferences.edit().apply {
            remove("thronos_wallet_address")
            remove("thronos_wallet_secret")
            apply()
        }
    }

    // MARK: - Models

    data class Wallet(
        val address: String,
        val secret: String
    )

    data class Token(
        val symbol: String,
        val name: String,
        val balance: Double,
        val decimals: Int,
        val color: String,
        val logo: String?
    )

    data class TokensResponse(
        val address: String,
        val tokens: List<Token>,
        @SerializedName("last_updated") val lastUpdated: String
    )

    data class TransactionRequest(
        val from: String,
        val to: String,
        val amount: Double,
        val token: String,
        val secret: String
    )

    data class TransactionResponse(
        val success: Boolean,
        val transaction: Transaction?
    )

    data class Transaction(
        val hash: String,
        val from: String,
        val to: String,
        val amount: Double,
        val token: String,
        val timestamp: String,
        val status: String
    )
}

// MARK: - Extension Functions

/**
 * Extension function to format wallet address
 */
fun String.toShortAddress(prefixLength: Int = 10, suffixLength: Int = 8): String {
    return if (this.length > prefixLength + suffixLength) {
        "${this.substring(0, prefixLength)}...${this.substring(this.length - suffixLength)}"
    } else {
        this
    }
}

/**
 * Extension function to validate Thronos address
 */
fun String.isValidThronosAddress(): Boolean {
    return this.startsWith("THR") && this.length > 10
}
