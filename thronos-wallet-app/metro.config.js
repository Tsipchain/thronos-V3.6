const { getDefaultConfig } = require('expo/metro-config');

const config = getDefaultConfig(__dirname);

// Support .cjs files used by some noble packages
config.resolver.sourceExts = [...config.resolver.sourceExts, 'cjs'];

module.exports = config;
