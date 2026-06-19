import express from 'express';
import cors from 'cors';
import helmet from 'helmet';
import rateLimit from 'express-ratelimit';
import dotenv from 'dotenv';
import { investorRoutes } from './routes/investor';
import { propertyRoutes } from './routes/property';
import { verifyRoutes } from './routes/verify';
import { smartContractRoutes } from './routes/smartContract';

dotenv.config();

const app = express();
const PORT = process.env.PORT || 3001;

// Security & Middleware
app.use(helmet());
app.use(cors({
  origin: process.env.FRONTEND_URL || 'http://localhost:3000',
  credentials: true
}));

const limiter = rateLimit({
  windowMs: 15 * 60 * 1000, // 15 minutes
  max: 100 // Limit each IP to 100 requests per windowMs
});

app.use(limiter);
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// Routes
app.use('/api/investors', investorRoutes);
app.use('/api/properties', propertyRoutes);
app.use('/api/verify', verifyRoutes);
app.use('/api/smartcontracts', smartContractRoutes);

// Health Check
app.get('/health', (req, res) => {
  res.json({ status: 'ok', timestamp: new Date().toISOString() });
});

// Error Handler
app.use((err: any, req: express.Request, res: express.Response, next: express.NextFunction) => {
  console.error('Error:', err);
  res.status(err.status || 500).json({
    error: err.message || 'Internal Server Error',
    timestamp: new Date().toISOString()
  });
});

// 404 Handler
app.use((req, res) => {
  res.status(404).json({ error: 'Not Found' });
});

// Start Server
app.listen(PORT, () => {
  console.log(`🚀 THRONOS Real Estate API running on http://localhost:${PORT}`);
  console.log(`📡 Environment: ${process.env.NODE_ENV || 'development'}`);
  console.log(`🔗 Thronoschain RPC: ${process.env.THRONOSCHAIN_RPC}`);
});

export default app;
