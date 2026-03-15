// URL polyfill must be first — Hermes engine doesn't implement URL natively
import 'react-native-url-polyfill/auto';

import { registerRootComponent } from 'expo';
import App from './App';

// registerRootComponent calls AppRegistry.registerComponent('main', () => App)
// and ensures the environment is set up correctly for Expo
registerRootComponent(App);
