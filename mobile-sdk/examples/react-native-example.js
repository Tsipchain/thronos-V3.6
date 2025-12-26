/**
 * Thronos Mobile SDK - React Native Example
 * Complete example app demonstrating all SDK features
 */

import React, { useEffect, useState } from 'react';
import {
    View,
    Text,
    TextInput,
    Button,
    FlatList,
    StyleSheet,
    Alert,
    TouchableOpacity,
    ActivityIndicator
} from 'react-native';
import ThronosSDK from 'thronos-mobile-sdk';

// Initialize SDK
const thronos = new ThronosSDK({
    apiUrl: 'http://localhost:5000',
    network: 'mainnet',
    autoSave: true
});

export default function ThronosWalletApp() {
    const [wallet, setWallet] = useState(null);
    const [balances, setBalances] = useState([]);
    const [loading, setLoading] = useState(true);
    const [activeTab, setActiveTab] = useState('balances'); // balances, send, history

    // Send form state
    const [sendTo, setSendTo] = useState('');
    const [sendAmount, setSendAmount] = useState('');
    const [sendToken, setSendToken] = useState('THR');

    // Import form state
    const [importAddress, setImportAddress] = useState('');
    const [importSecret, setImportSecret] = useState('');

    // Transaction history
    const [transactions, setTransactions] = useState([]);

    useEffect(() => {
        loadWallet();
    }, []);

    // Load wallet from storage
    const loadWallet = async () => {
        setLoading(true);
        try {
            const w = await thronos.getWallet();
            setWallet(w);

            if (w) {
                await loadBalances();
                await loadTransactionHistory();
            }
        } catch (error) {
            Alert.alert('Error', error.message);
        } finally {
            setLoading(false);
        }
    };

    // Load token balances
    const loadBalances = async () => {
        try {
            const data = await thronos.getBalances(null, false);
            setBalances(data.tokens);
        } catch (error) {
            Alert.alert('Error', 'Failed to load balances');
        }
    };

    // Load transaction history
    const loadTransactionHistory = async () => {
        try {
            const txs = await thronos.getTransactionHistory();
            setTransactions(txs);
        } catch (error) {
            console.error('Failed to load transactions:', error);
        }
    };

    // Create new wallet
    const handleCreateWallet = async () => {
        setLoading(true);
        try {
            const newWallet = await thronos.createWallet();

            Alert.alert(
                'Wallet Created',
                `Address: ${newWallet.address}\n\nSecret: ${newWallet.secret}\n\n⚠️ Please save your secret key securely!`,
                [
                    {
                        text: 'I\'ve Saved It',
                        onPress: () => {
                            setWallet(newWallet);
                            loadBalances();
                        }
                    }
                ]
            );
        } catch (error) {
            Alert.alert('Error', error.message);
        } finally {
            setLoading(false);
        }
    };

    // Import existing wallet
    const handleImportWallet = async () => {
        if (!importAddress || !importSecret) {
            Alert.alert('Error', 'Please enter both address and secret key');
            return;
        }

        setLoading(true);
        try {
            const w = await thronos.importWallet(importAddress, importSecret);
            setWallet(w);
            setImportAddress('');
            setImportSecret('');
            await loadBalances();
            Alert.alert('Success', 'Wallet imported successfully');
        } catch (error) {
            Alert.alert('Error', error.message);
        } finally {
            setLoading(false);
        }
    };

    // Send transaction
    const handleSendTransaction = async () => {
        if (!sendTo || !sendAmount) {
            Alert.alert('Error', 'Please fill all fields');
            return;
        }

        if (!sendTo.startsWith('THR')) {
            Alert.alert('Error', 'Invalid recipient address');
            return;
        }

        const amount = parseFloat(sendAmount);
        if (isNaN(amount) || amount <= 0) {
            Alert.alert('Error', 'Invalid amount');
            return;
        }

        setLoading(true);
        try {
            const result = await thronos.sendTransaction(sendTo, amount, sendToken);

            if (result.success) {
                Alert.alert('Success', 'Transaction sent successfully!');
                setSendTo('');
                setSendAmount('');
                await loadBalances();
                await loadTransactionHistory();
            } else {
                Alert.alert('Error', 'Transaction failed');
            }
        } catch (error) {
            Alert.alert('Error', error.message);
        } finally {
            setLoading(false);
        }
    };

    // Disconnect wallet
    const handleDisconnect = () => {
        Alert.alert(
            'Disconnect Wallet',
            'Are you sure you want to disconnect your wallet?',
            [
                { text: 'Cancel', style: 'cancel' },
                {
                    text: 'Disconnect',
                    style: 'destructive',
                    onPress: async () => {
                        await thronos.disconnect();
                        setWallet(null);
                        setBalances([]);
                        setTransactions([]);
                    }
                }
            ]
        );
    };

    // Refresh data
    const handleRefresh = async () => {
        setLoading(true);
        await loadBalances();
        await loadTransactionHistory();
        setLoading(false);
    };

    // Render not connected screen
    if (!wallet) {
        return (
            <View style={styles.container}>
                <Text style={styles.title}>Thronos Wallet</Text>

                <View style={styles.welcomeContainer}>
                    <Text style={styles.welcomeText}>Welcome to Thronos Network</Text>
                    <Text style={styles.subtitle}>Create or import a wallet to get started</Text>
                </View>

                <Button
                    title="Create New Wallet"
                    onPress={handleCreateWallet}
                    disabled={loading}
                />

                <View style={styles.divider} />

                <Text style={styles.sectionTitle}>Import Existing Wallet</Text>

                <TextInput
                    style={styles.input}
                    placeholder="Wallet Address (THR...)"
                    value={importAddress}
                    onChangeText={setImportAddress}
                    autoCapitalize="none"
                />

                <TextInput
                    style={styles.input}
                    placeholder="Secret Key"
                    value={importSecret}
                    onChangeText={setImportSecret}
                    secureTextEntry
                    autoCapitalize="none"
                />

                <Button
                    title="Import Wallet"
                    onPress={handleImportWallet}
                    disabled={loading}
                />

                {loading && <ActivityIndicator style={styles.loader} size="large" color="#00ff00" />}
            </View>
        );
    }

    // Render connected screen
    return (
        <View style={styles.container}>
            <View style={styles.header}>
                <Text style={styles.title}>Thronos Wallet</Text>
                <TouchableOpacity onPress={handleDisconnect}>
                    <Text style={styles.disconnectBtn}>✖</Text>
                </TouchableOpacity>
            </View>

            <View style={styles.addressContainer}>
                <Text style={styles.addressLabel}>Address:</Text>
                <Text style={styles.address}>
                    {wallet.address.substring(0, 12)}...{wallet.address.substring(wallet.address.length - 8)}
                </Text>
            </View>

            {/* Tabs */}
            <View style={styles.tabs}>
                <TouchableOpacity
                    style={[styles.tab, activeTab === 'balances' && styles.activeTab]}
                    onPress={() => setActiveTab('balances')}
                >
                    <Text style={styles.tabText}>Balances</Text>
                </TouchableOpacity>
                <TouchableOpacity
                    style={[styles.tab, activeTab === 'send' && styles.activeTab]}
                    onPress={() => setActiveTab('send')}
                >
                    <Text style={styles.tabText}>Send</Text>
                </TouchableOpacity>
                <TouchableOpacity
                    style={[styles.tab, activeTab === 'history' && styles.activeTab]}
                    onPress={() => setActiveTab('history')}
                >
                    <Text style={styles.tabText}>History</Text>
                </TouchableOpacity>
            </View>

            {/* Balances Tab */}
            {activeTab === 'balances' && (
                <View style={styles.content}>
                    <Button title="🔄 Refresh" onPress={handleRefresh} disabled={loading} />

                    {loading ? (
                        <ActivityIndicator style={styles.loader} size="large" color="#00ff00" />
                    ) : (
                        <FlatList
                            data={balances}
                            keyExtractor={(item) => item.symbol}
                            renderItem={({ item }) => (
                                <View style={styles.tokenItem}>
                                    <View>
                                        <Text style={styles.tokenSymbol}>{item.symbol}</Text>
                                        <Text style={styles.tokenName}>{item.name}</Text>
                                    </View>
                                    <Text style={[styles.tokenBalance, { color: item.color }]}>
                                        {item.balance.toFixed(item.decimals)}
                                    </Text>
                                </View>
                            )}
                            ListEmptyComponent={
                                <Text style={styles.emptyText}>No tokens found</Text>
                            }
                        />
                    )}
                </View>
            )}

            {/* Send Tab */}
            {activeTab === 'send' && (
                <View style={styles.content}>
                    <Text style={styles.label}>Token</Text>
                    <TextInput
                        style={styles.input}
                        placeholder="THR"
                        value={sendToken}
                        onChangeText={setSendToken}
                    />

                    <Text style={styles.label}>Recipient Address</Text>
                    <TextInput
                        style={styles.input}
                        placeholder="THR..."
                        value={sendTo}
                        onChangeText={setSendTo}
                        autoCapitalize="none"
                    />

                    <Text style={styles.label}>Amount</Text>
                    <TextInput
                        style={styles.input}
                        placeholder="0.00"
                        value={sendAmount}
                        onChangeText={setSendAmount}
                        keyboardType="decimal-pad"
                    />

                    <Button
                        title="Send Transaction"
                        onPress={handleSendTransaction}
                        disabled={loading}
                    />

                    {loading && <ActivityIndicator style={styles.loader} size="large" color="#00ff00" />}
                </View>
            )}

            {/* History Tab */}
            {activeTab === 'history' && (
                <View style={styles.content}>
                    <FlatList
                        data={transactions}
                        keyExtractor={(item) => item.hash}
                        renderItem={({ item }) => (
                            <View style={styles.txItem}>
                                <Text style={styles.txHash}>{item.hash.substring(0, 16)}...</Text>
                                <Text style={styles.txDetails}>
                                    {item.amount} {item.token}
                                </Text>
                                <Text style={styles.txTime}>{item.timestamp}</Text>
                            </View>
                        )}
                        ListEmptyComponent={
                            <Text style={styles.emptyText}>No transactions found</Text>
                        }
                    />
                </View>
            )}
        </View>
    );
}

const styles = StyleSheet.create({
    container: {
        flex: 1,
        backgroundColor: '#000',
        padding: 20
    },
    header: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: 20
    },
    title: {
        fontSize: 24,
        fontWeight: 'bold',
        color: '#00ff00'
    },
    disconnectBtn: {
        color: '#ff0000',
        fontSize: 20
    },
    welcomeContainer: {
        alignItems: 'center',
        marginVertical: 40
    },
    welcomeText: {
        fontSize: 20,
        color: '#00ff00',
        marginBottom: 10
    },
    subtitle: {
        fontSize: 14,
        color: '#888'
    },
    addressContainer: {
        backgroundColor: '#111',
        padding: 15,
        borderRadius: 8,
        borderWidth: 1,
        borderColor: '#00ff00',
        marginBottom: 20
    },
    addressLabel: {
        fontSize: 12,
        color: '#888',
        marginBottom: 5
    },
    address: {
        fontSize: 14,
        color: '#00ff00',
        fontFamily: 'monospace'
    },
    tabs: {
        flexDirection: 'row',
        marginBottom: 20
    },
    tab: {
        flex: 1,
        padding: 12,
        alignItems: 'center',
        backgroundColor: '#111',
        borderWidth: 1,
        borderColor: '#333'
    },
    activeTab: {
        backgroundColor: '#222',
        borderBottomColor: '#00ff00',
        borderBottomWidth: 2
    },
    tabText: {
        color: '#00ff00',
        fontWeight: 'bold'
    },
    content: {
        flex: 1
    },
    tokenItem: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        padding: 15,
        backgroundColor: '#111',
        borderRadius: 8,
        borderWidth: 1,
        borderColor: '#00ff00',
        marginBottom: 10
    },
    tokenSymbol: {
        fontSize: 16,
        fontWeight: 'bold',
        color: '#00ff00'
    },
    tokenName: {
        fontSize: 12,
        color: '#888'
    },
    tokenBalance: {
        fontSize: 16,
        fontWeight: 'bold',
        fontFamily: 'monospace'
    },
    label: {
        fontSize: 12,
        color: '#888',
        marginBottom: 5,
        marginTop: 15
    },
    input: {
        backgroundColor: '#111',
        borderWidth: 1,
        borderColor: '#00ff00',
        borderRadius: 8,
        padding: 12,
        color: '#00ff00',
        marginBottom: 10
    },
    divider: {
        height: 30
    },
    sectionTitle: {
        fontSize: 16,
        color: '#00ff00',
        marginBottom: 15
    },
    loader: {
        marginTop: 20
    },
    emptyText: {
        textAlign: 'center',
        color: '#888',
        marginTop: 40,
        fontSize: 14
    },
    txItem: {
        padding: 15,
        backgroundColor: '#111',
        borderRadius: 8,
        borderWidth: 1,
        borderColor: '#00ff00',
        marginBottom: 10
    },
    txHash: {
        fontSize: 12,
        color: '#00ff00',
        fontFamily: 'monospace'
    },
    txDetails: {
        fontSize: 14,
        color: '#fff',
        marginTop: 5
    },
    txTime: {
        fontSize: 10,
        color: '#888',
        marginTop: 5
    }
});
