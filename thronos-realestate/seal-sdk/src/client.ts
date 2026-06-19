import axios, { AxiosInstance } from 'axios';
import { ethers } from 'ethers';

export interface SealConfig {
  apiUrl: string;
  rpcUrl: string;
  contractAddress: string;
  timeout?: number;
}

export interface PropertyData {
  propertyId: string;
  propertyName: string;
  location: string;
  ownerAddress: string;
  metadata?: Record<string, any>;
}

export interface SealResponse {
  id: string;
  propertyId: string;
  sealHash: string;
  contractAddress: string;
  transactionHash: string;
  timestamp: string;
  status: 'verified' | 'pending' | 'failed';
}

/**
 * THRONOS Seal SDK Client
 * Provides simple interface for creating and verifying property seals
 */
export class SealClient {
  private apiClient: AxiosInstance;
  private config: SealConfig;
  private provider: ethers.JsonRpcProvider;

  constructor(config: SealConfig) {
    this.config = config;
    this.apiClient = axios.create({
      baseURL: config.apiUrl,
      timeout: config.timeout || 30000,
      headers: {
        'Content-Type': 'application/json'
      }
    });
    this.provider = new ethers.JsonRpcProvider(config.rpcUrl);
  }

  /**
   * Create a new seal for a property
   */
  async createSeal(property: PropertyData): Promise<SealResponse> {
    try {
      const response = await this.apiClient.post('/seals/create', {
        propertyId: property.propertyId,
        propertyName: property.propertyName,
        location: property.location,
        ownerAddress: property.ownerAddress,
        metadata: property.metadata || {}
      });

      return response.data.seal;
    } catch (error) {
      throw new Error(`Failed to create seal: ${error}`);
    }
  }

  /**
   * Get seal details
   */
  async getSeal(sealId: string): Promise<SealResponse> {
    try {
      const response = await this.apiClient.get(`/seals/${sealId}`);
      return response.data.seal;
    } catch (error) {
      throw new Error(`Failed to fetch seal: ${error}`);
    }
  }

  /**
   * Verify a seal's authenticity
   */
  async verifySeal(sealId: string): Promise<{
    isValid: boolean;
    blockNumber: number;
    gasUsed: string;
  }> {
    try {
      const response = await this.apiClient.post(`/seals/${sealId}/verify`);
      return response.data.verification;
    } catch (error) {
      throw new Error(`Seal verification failed: ${error}`);
    }
  }

  /**
   * Get all seals for a property
   */
  async getPropertySeals(propertyId: string): Promise<SealResponse[]> {
    try {
      const response = await this.apiClient.get(`/seals/property/${propertyId}`);
      return response.data.seals;
    } catch (error) {
      throw new Error(`Failed to fetch property seals: ${error}`);
    }
  }

  /**
   * Public verification (anyone can verify without authentication)
   */
  async publicVerify(sealHash: string): Promise<{
    isValid: boolean;
    blockNumber: number;
    verifiedAt: string;
  }> {
    try {
      const response = await this.apiClient.get(`/verify/public/${sealHash}`);
      return response.data.verification;
    } catch (error) {
      throw new Error(`Public verification failed: ${error}`);
    }
  }

  /**
   * Register a new property with seal
   */
  async registerProperty(
    name: string,
    location: string,
    ownerAddress: string,
    documents?: { type: string; ipfsHash: string }[]
  ): Promise<{ propertyId: string; sealId: string }> {
    try {
      const response = await this.apiClient.post('/properties/register', {
        name,
        location,
        ownerAddress,
        documents: documents || []
      });

      return {
        propertyId: response.data.property.id,
        sealId: response.data.property.seal.id
      };
    } catch (error) {
      throw new Error(`Property registration failed: ${error}`);
    }
  }

  /**
   * Get property details with seal history
   */
  async getProperty(propertyId: string): Promise<any> {
    try {
      const response = await this.apiClient.get(`/properties/${propertyId}`);
      return response.data.property;
    } catch (error) {
      throw new Error(`Failed to fetch property: ${error}`);
    }
  }

  /**
   * Create bulk seals
   */
  async createBulkSeals(properties: PropertyData[]): Promise<SealResponse[]> {
    try {
      const response = await this.apiClient.post('/seals/batch', {
        properties
      });

      return response.data.seals;
    } catch (error) {
      throw new Error(`Bulk seal creation failed: ${error}`);
    }
  }

  /**
   * Sign message with private key (for testing only)
   */
  signMessage(message: string, privateKey: string): {
    signature: string;
    hash: string;
  } {
    const wallet = new ethers.Wallet(privateKey);
    const hash = ethers.hashMessage(message);
    const signature = wallet.signingKey.sign(hash).serialized;

    return { signature, hash };
  }

  /**
   * Verify merkle proof
   */
  async verifyMerkleProof(
    leaf: string,
    proof: string[],
    root: string
  ): Promise<boolean> {
    try {
      const response = await this.apiClient.post('/verify/merkle', {
        leaf,
        proof,
        root
      });

      return response.data.isValid;
    } catch (error) {
      throw new Error(`Merkle verification failed: ${error}`);
    }
  }

  /**
   * Get health check
   */
  async getHealth(): Promise<{ status: string; version: string }> {
    try {
      const response = await this.apiClient.get('/health');
      return response.data;
    } catch (error) {
      throw new Error(`Health check failed: ${error}`);
    }
  }
}

export default SealClient;
