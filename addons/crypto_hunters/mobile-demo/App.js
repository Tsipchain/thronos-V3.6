import React, { useState, useEffect } from 'react';
import { View, Text, Button, TextInput, StyleSheet, ScrollView } from 'react-native';

// Adjust this constant if your backend runs on another host or port
const API = 'http://localhost:3000';

const Row = ({ children }) => <View style={styles.row}>{children}</View>;

function Home({ routeTo, wallet, setWallet }) {
  return (
    <ScrollView contentContainerStyle={styles.screen}>
      <Text style={styles.h1}>Crypto Hunters</Text>
      <Text style={styles.text}>XRPL Wallet (blind):</Text>
      <TextInput
        style={styles.input}
        value={wallet}
        onChangeText={setWallet}
        placeholder="Enter wallet address"
      />
      <Row>
        <Button title="Story" onPress={() => routeTo('story')} />
        <Button title="Missions" onPress={() => routeTo('missions')} />
      </Row>
      <Row>
        <Button title="Wallet" onPress={() => routeTo('wallet')} />
        <Button title="Items" onPress={() => routeTo('items')} />
      </Row>
      <Row>
        <Button title="Inventory" onPress={() => routeTo('inventory')} />
        <Button title="Bridge" onPress={() => routeTo('bridge')} />
      </Row>
    </ScrollView>
  );
}

function Bridge({ routeTo, wallet }) {
  const [thrAddress, setThrAddress] = useState('');
  const [amount, setAmount] = useState('');
  const [direction, setDirection] = useState('drx-to-thr');
  const [msg, setMsg] = useState('');
  const submit = async () => {
    if (!amount) return setMsg('Enter amount');
    const amt = parseFloat(amount);
    if (!amt || amt <= 0) return setMsg('Invalid amount');
    try {
      let body;
      let url;
      if (direction === 'drx-to-thr') {
        if (!wallet) return setMsg('Set wallet first');
        if (!thrAddress) return setMsg('Enter Thronos address');
        url = `${API}/api/bridge/drx-to-thr`;
        body = { wallet, amount: amt, thrAddress };
      } else {
        // thr-to-drx
        if (!wallet) return setMsg('Set wallet first');
        if (!thrAddress) return setMsg('Enter Thronos address');
        url = `${API}/api/bridge/thr-to-drx`;
        body = { thrAddress, amount: amt, wallet };
      }
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
      const data = await res.json();
      setMsg(JSON.stringify(data, null, 2));
    } catch (e) {
      setMsg(e.message);
    }
  };
  return (
    <ScrollView contentContainerStyle={styles.screen}>
      <Text style={styles.h1}>Bridge</Text>
      <Text style={styles.text}>Direction:</Text>
      <Row>
        <Button
          title="DRX → Thronos"
          onPress={() => setDirection('drx-to-thr')}
          color={direction === 'drx-to-thr' ? '#10b981' : undefined}
        />
        <Button
          title="Thronos → DRX"
          onPress={() => setDirection('thr-to-drx')}
          color={direction === 'thr-to-drx' ? '#10b981' : undefined}
        />
      </Row>
      <Text style={styles.text}>Amount:</Text>
      <TextInput
        style={styles.input}
        value={amount}
        onChangeText={setAmount}
        placeholder="Enter amount"
        keyboardType="numeric"
      />
      <Text style={styles.text}>Thronos Address:</Text>
      <TextInput
        style={styles.input}
        value={thrAddress}
        onChangeText={setThrAddress}
        placeholder="THR..."
      />
      <Row>
        <Button title="Submit" onPress={submit} />
        <Button title="← Back" onPress={() => routeTo('home')} />
      </Row>
      <Text style={styles.mono}>{msg}</Text>
    </ScrollView>
  );
}

function Story({ routeTo }) {
  return (
    <ScrollView contentContainerStyle={styles.screen}>
      <Text style={styles.h1}>Η Γένεση</Text>
      <Text style={styles.par}>Το παιχνίδι ξεκινά στην Ελλάδα του 2012.  Ο SAfA εξερευνά το mining και το blockchain,
        γνωρίζεται ξανά με τον Nato Saka και στη συνέχεια σχηματίζει μία ομάδα από
        χάκερ και μηχανικούς για να προστατεύσουν τα αποκεντρωμένα δίκτυα.
      </Text>
      <Text style={styles.h2}>Πράξη Ι – Σπινθήρας</Text>
      <Text style={styles.par}>Ο SAfA στήνει το πρώτο του rig και μαθαίνει για hash και nonces.  Ένα bull run
        τον γοητεύει και τον συντρίβει.  Καταλαβαίνει πως χρειάζεται ομάδα.</Text>
      <Text style={styles.h2}>Πράξη ΙΙ – Σχηματισμός</Text>
      <Text style={styles.par}>Η Niva φέρνει το ταλέντο της στην κρυπτογράφηση.  Η Kyra χτίζει ασπίδες.
        Η Luna κρατά τους διακομιστές ζωντανούς.  Μαζί αποτρέπουν επιθέσεις του
        Dark Node.</Text>
      <Text style={styles.h2}>Πράξη ΙΙΙ – Αποκάλυψη</Text>
      <Text style={styles.par}>Ο Zayne εμφανίζεται με αποδείξεις ότι ο εχθρός είναι μεγαλύτερος απ’ ό,τι
        πιστεύαμε.  Οι Hunters πρέπει να αποφασίσουν αν θα συνεργαστούν με
        φορείς εξουσίας ή θα παραμείνουν ανεξάρτητοι.</Text>
      <Text style={styles.h2}>Πράξη IV – Ανύψωση</Text>
      <Text style={styles.par}>Η τελική μάχη απαιτεί πλήρη συνεργασία και συνδυασμό των ικανοτήτων όλων.
        Η Ελλάδα λανσάρει αποκεντρωμένη στοίβα πολιτών, ενώ ο Dark Node
        υποχωρεί… προσωρινά.</Text>
      <Button title="← Back" onPress={() => routeTo('home')} />
    </ScrollView>
  );
}

function Missions({ routeTo, wallet }) {
  const [missions, setMissions] = useState([]);
  const [msg, setMsg] = useState('');
  useEffect(() => {
    fetch(`${API}/api/missions`).then((r) => r.json()).then(setMissions);
  }, []);
  const complete = async (id) => {
    if (!wallet) return setMsg('Set wallet first');
    const res = await fetch(`${API}/api/missions/complete`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ wallet, missionId: id })
    });
    const data = await res.json();
    setMsg(JSON.stringify(data, null, 2));
  };
  return (
    <ScrollView contentContainerStyle={styles.screen}>
      <Text style={styles.h1}>Missions</Text>
      {missions.map((m) => (
        <View key={m.id} style={styles.card}>
          <Text style={styles.h3}>[{m.tier}] {m.id} – {m.title}</Text>
          <Text style={styles.text}>Objective: {m.objective}</Text>
          <Text style={styles.text}>Reward: {m.reward_drx} DRX</Text>
          <Button title="Complete" onPress={() => complete(m.id)} />
        </View>
      ))}
      <Text style={styles.mono}>{msg}</Text>
      <Button title="← Back" onPress={() => routeTo('home')} />
    </ScrollView>
  );
}

function Wallet({ routeTo, wallet }) {
  const [status, setStatus] = useState('');
  const refresh = async () => {
    if (!wallet) return setStatus('Set wallet first');
    const res = await fetch(`${API}/api/status/${wallet}`);
    setStatus(JSON.stringify(await res.json(), null, 2));
  };
  const withdraw = async () => {
    if (!wallet) return setStatus('Set wallet first');
    const res = await fetch(`${API}/api/withdraw/${wallet}`, { method: 'POST' });
    setStatus(JSON.stringify(await res.json(), null, 2));
  };
  useEffect(() => { refresh(); }, [wallet]);
  return (
    <ScrollView contentContainerStyle={styles.screen}>
      <Text style={styles.h1}>Wallet</Text>
      <Row>
        <Button title="Refresh" onPress={refresh} />
        <Button title="Withdraw" onPress={withdraw} />
      </Row>
      <Text style={styles.mono}>{status}</Text>
      <Button title="← Back" onPress={() => routeTo('home')} />
    </ScrollView>
  );
}

function Items({ routeTo, wallet }) {
  const [items, setItems] = useState([]);
  const [msg, setMsg] = useState('');
  useEffect(() => {
    fetch(`${API}/api/items`).then((r) => r.json()).then(setItems);
  }, []);
  const buy = async (id) => {
    if (!wallet) return setMsg('Set wallet first');
    const res = await fetch(`${API}/api/items/buy/${id}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ wallet })
    });
    const data = await res.json();
    setMsg(JSON.stringify(data, null, 2));
  };
  return (
    <ScrollView contentContainerStyle={styles.screen}>
      <Text style={styles.h1}>Items Shop</Text>
      {items.map((i) => (
        <View key={i.id} style={styles.card}>
          <Text style={styles.h3}>{i.name}</Text>
          <Text style={styles.text}>{i.desc}</Text>
          <Text style={styles.text}>Price: {i.price_drx} DRX</Text>
          <Button title="Buy" onPress={() => buy(i.id)} />
        </View>
      ))}
      <Text style={styles.mono}>{msg}</Text>
      <Button title="← Back" onPress={() => routeTo('home')} />
    </ScrollView>
  );
}

function Inventory({ routeTo, wallet }) {
  const [data, setData] = useState('');
  const refresh = async () => {
    if (!wallet) return setData('Set wallet first');
    const res = await fetch(`${API}/api/status/${wallet}`);
    setData(JSON.stringify(await res.json(), null, 2));
  };
  useEffect(() => { refresh(); }, [wallet]);
  return (
    <ScrollView contentContainerStyle={styles.screen}>
      <Text style={styles.h1}>Inventory</Text>
      <Button title="Refresh" onPress={refresh} />
      <Text style={styles.mono}>{data}</Text>
      <Button title="← Back" onPress={() => routeTo('home')} />
    </ScrollView>
  );
}

export default function App() {
  const [route, setRoute] = useState('home');
  const [wallet, setWallet] = useState('');
  const routeTo = (r) => setRoute(r);
  return (
    <View style={styles.container}>
      {route === 'home' && <Home routeTo={routeTo} wallet={wallet} setWallet={setWallet} />}
      {route === 'story' && <Story routeTo={routeTo} />}
      {route === 'missions' && <Missions routeTo={routeTo} wallet={wallet} />}
      {route === 'wallet' && <Wallet routeTo={routeTo} wallet={wallet} />}
      {route === 'items' && <Items routeTo={routeTo} wallet={wallet} />}
      {route === 'inventory' && <Inventory routeTo={routeTo} wallet={wallet} />}
      {route === 'bridge' && <Bridge routeTo={routeTo} wallet={wallet} />}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, padding: 24, paddingTop: 48, backgroundColor: '#0b1020' },
  screen: { gap: 12 },
  h1: { fontSize: 28, fontWeight: 'bold', color: '#fff' },
  h2: { fontSize: 20, fontWeight: 'bold', color: '#ffd700', marginTop: 16 },
  h3: { fontSize: 16, fontWeight: 'bold', color: '#fff' },
  text: { color: '#d1d5db' },
  par: { color: '#d1d5db', marginBottom: 12 },
  input: { backgroundColor: '#fff', padding: 10, borderRadius: 8 },
  row: { flexDirection: 'row', gap: 12, marginTop: 8 },
  card: { backgroundColor: '#141a33', padding: 12, borderRadius: 12 },
  mono: { color: '#10b981', fontFamily: 'Courier', marginTop: 12 }
});