// Jest setup file for additional test configuration

// Suppress console errors and warnings during tests
global.console = {
  ...console,
  error: jest.fn(),
  warn: jest.fn(),
};

// Set test timeout
jest.setTimeout(10000);
