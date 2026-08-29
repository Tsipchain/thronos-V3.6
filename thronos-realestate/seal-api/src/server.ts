import express from 'express';
import cors from 'cors';
import helmet from 'helmet';
import dotenv from 'dotenv';
import { sealRoutes } from './routes/seals';
import { verifyRoutes } from './routes/verify';
import { propertyRoutes } from './routes/properties';
import { logger } from './lib/logger';

dotenv.config();

const app = express();
const PORT = process.env.PORT || 3002;

// Security
app.use(helmet());
app.use(cors({
  origin: process.env.ALLOWED_ORIGINS?.split(',') || '*',
  credentials: true
}));

// Middleware
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// Logging
app.use((req, res, next) => {
  logger.info(`${req.method} ${req.path}`);
  next();
});

// Routes
app.use('/api/seals', sealRoutes);
app.use('/api/verify', verifyRoutes);
app.use('/api/properties', propertyRoutes);

// Health Check
app.get('/health', (req, res) => {
  res.json({
    status: 'ok',
    service: 'THRONOS Seal API',
    timestamp: new Date().toISOString(),
    blockchain: process.env.THRONOSCHAIN_RPC,
    version: '1.0.0'
  });
});

// 404 Handler
app.use((req, res) => {
  res.status(404).json({ error: 'Endpoint not found' });
});

// Error Handler
app.use((err: any, req: express.Request, res: express.Response, next: express.NextFunction) => {
  logger.error('Error:', err);
  res.status(err.status || 500).json({
    error: err.message || 'Internal Server Error',
    timestamp: new Date().toISOString()
  });
});

// Start Server
app.listen(PORT, () => {
  logger.info(`🔐 THRONOS Seal API running on http://localhost:${PORT}`);
  logger.info(`📡 Thronoschain RPC: ${process.env.THRONOSCHAIN_RPC}`);
  logger.info(`🔗 Contract Address: ${process.env.PROPERTY_SEAL_CONTRACT}`);
});

export default app;
