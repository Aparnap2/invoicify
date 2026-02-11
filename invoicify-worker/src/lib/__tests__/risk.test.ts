import { describe, it, expect } from 'vitest';
import { 
  calculateZScore, 
  calculateRiskScore, 
  getRiskLevel,
  explainRisk 
} from '../risk';

describe('Risk Calculation', () => {
  describe('calculateZScore', () => {
    it('should return 0.5 for unknown vendors (less than 5 history)', () => {
      const history: number[] = [100, 110];
      const score = calculateZScore(150, history);
      expect(score).toBe(0.5);
    });

    it('should calculate z-score correctly for normal distribution', () => {
      const history = [100, 110, 120, 130, 140];
      const amount = 150;
      const score = calculateZScore(amount, history);
      
      // Mean = 120, StdDev ≈ 15.81
      // Z = |150 - 120| / 15.81 ≈ 1.90
      expect(score).toBeGreaterThan(1.8);
      expect(score).toBeLessThan(2.0);
    });

    it('should return 0 for identical amounts', () => {
      const history = [100, 100, 100, 100, 100];
      const score = calculateZScore(100, history);
      expect(score).toBe(0);
    });

    it('should handle negative z-scores correctly', () => {
      const history = [100, 110, 120, 130, 140];
      const amount = 50; // Much lower than mean
      const score = calculateZScore(amount, history);
      
      expect(score).toBeGreaterThan(3);
    });
  });

  describe('calculateRiskScore', () => {
    it('should return low risk for normal amounts with trusted vendor', () => {
      const history = [100, 110, 120, 130, 140];
      const risk = calculateRiskScore(125, history, 5);
      
      expect(risk).toBeLessThan(0.3);
    });

    it('should return high risk for anomalous amounts', () => {
      const history = [100, 110, 120, 130, 140];
      const risk = calculateRiskScore(500, history, 5);
      
      expect(risk).toBeGreaterThan(0.5);
    });

    it('should penalize new vendors', () => {
      const history: number[] = [100];
      const risk = calculateRiskScore(100, history, 1);
      
      expect(risk).toBeGreaterThan(0.3); // New vendor penalty
    });

    it('should penalize high amounts', () => {
      const history = [5000, 5100, 4900, 5200, 4800];
      const risk = calculateRiskScore(15000, history, 5);
      
      expect(risk).toBeGreaterThan(0.2); // High amount penalty
    });

    it('should penalize low trust levels', () => {
      const history = [100, 110, 120, 130, 140];
      const lowTrust = calculateRiskScore(125, history, 1);
      const highTrust = calculateRiskScore(125, history, 5);
      
      expect(lowTrust).toBeGreaterThan(highTrust);
    });

    it('should never exceed 1.0', () => {
      const history: number[] = [];
      const risk = calculateRiskScore(100000, history, 1);
      
      expect(risk).toBeLessThanOrEqual(1.0);
    });

    it('should detect high variance in vendor history', () => {
      const history = [100, 500, 100, 500, 100]; // High variance
      const risk = calculateRiskScore(300, history, 5);
      
      // Should have some penalty for high variance
      expect(risk).toBeGreaterThan(0);
    });
  });

  describe('getRiskLevel', () => {
    it('should return LOW for scores < 0.3', () => {
      expect(getRiskLevel(0.1)).toBe('LOW');
      expect(getRiskLevel(0.29)).toBe('LOW');
    });

    it('should return MEDIUM for scores 0.3-0.6', () => {
      expect(getRiskLevel(0.3)).toBe('MEDIUM');
      expect(getRiskLevel(0.5)).toBe('MEDIUM');
      expect(getRiskLevel(0.59)).toBe('MEDIUM');
    });

    it('should return HIGH for scores 0.6-0.8', () => {
      expect(getRiskLevel(0.6)).toBe('HIGH');
      expect(getRiskLevel(0.7)).toBe('HIGH');
      expect(getRiskLevel(0.79)).toBe('HIGH');
    });

    it('should return CRITICAL for scores >= 0.8', () => {
      expect(getRiskLevel(0.8)).toBe('CRITICAL');
      expect(getRiskLevel(0.95)).toBe('CRITICAL');
      expect(getRiskLevel(1.0)).toBe('CRITICAL');
    });
  });

  describe('explainRisk', () => {
    it('should explain z-score anomalies', () => {
      const history = [100, 110, 120, 130, 140];
      const explanations = explainRisk(200, history, 5, 0.8);
      
      expect(explanations.some(e => e.includes('standard deviations'))).toBe(true);
    });

    it('should explain high amounts', () => {
      const history = [100, 110, 120, 130, 140];
      const explanations = explainRisk(15000, history, 5, 0.9);
      
      expect(explanations.some(e => e.includes('High amount'))).toBe(true);
    });

    it('should explain new vendors', () => {
      const history: number[] = [100];
      const explanations = explainRisk(100, history, 5, 0.5);
      
      expect(explanations.some(e => e.includes('New vendor'))).toBe(true);
    });

    it('should explain low trust', () => {
      const history = [100, 110, 120, 130, 140];
      const explanations = explainRisk(125, history, 1, 0.4);
      
      expect(explanations.some(e => e.includes('Low trust'))).toBe(true);
    });

    it('should explain high variance', () => {
      const history = [100, 500, 100, 500, 100];
      const explanations = explainRisk(300, history, 5, 0.5);
      
      expect(explanations.some(e => e.includes('variance'))).toBe(true);
    });

    it('should return empty array for low risk', () => {
      const history = [100, 110, 120, 130, 140];
      const explanations = explainRisk(120, history, 5, 0.1);
      
      expect(explanations.length).toBe(0);
    });
  });
});
