export interface RiskFactors {
  zScore: number;
  amountAnomaly: boolean;
  unknownVendor: boolean;
  highAmount: boolean;
}

export function calculateZScore(amount: number, history: number[]): number {
  if (history.length < 5) {
    return 0.5; // Unknown vendor - medium risk
  }
  
  const mean = history.reduce((a, b) => a + b, 0) / history.length;
  const variance = history.reduce((sum, val) => sum + Math.pow(val - mean, 2), 0) / history.length;
  const stdDev = Math.sqrt(variance);
  
  if (stdDev === 0) {
    return amount === mean ? 0 : 1; // All amounts identical
  }
  
  return Math.abs((amount - mean) / stdDev);
}

export function calculateRiskScore(
  amount: number,
  history: number[],
  trustLevel: number = 1,
  vendorName?: string
): number {
  // Calculate z-score for amount anomaly
  const zScore = calculateZScore(amount, history);
  
  // Base risk from z-score (normalize to 0-1)
  let riskScore = Math.min(zScore / 3, 1.0);
  
  // Signal: High amount
  if (amount > 10000) {
    riskScore += 0.2;
  }
  
  // Signal: Unknown vendor (less than 3 historical invoices)
  if (history.length < 3) {
    riskScore += 0.3;
  }
  
  // Signal: Low trust level
  if (trustLevel <= 2) {
    riskScore += 0.2;
  }
  
  // Signal: Large variance in history
  if (history.length >= 5) {
    const mean = history.reduce((a, b) => a + b, 0) / history.length;
    const variance = history.reduce((sum, val) => sum + Math.pow(val - mean, 2), 0) / history.length;
    const stdDev = Math.sqrt(variance);
    const cv = stdDev / mean; // Coefficient of variation
    
    if (cv > 0.5) {
      riskScore += 0.1; // High variance in vendor's invoices
    }
  }
  
  // Cap at 1.0
  return Math.min(riskScore, 1.0);
}

export function getRiskLevel(riskScore: number): 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL' {
  if (riskScore < 0.3) return 'LOW';
  if (riskScore < 0.6) return 'MEDIUM';
  if (riskScore < 0.8) return 'HIGH';
  return 'CRITICAL';
}

export function explainRisk(
  amount: number,
  history: number[],
  trustLevel: number,
  riskScore: number
): string[] {
  const explanations: string[] = [];
  
  const zScore = calculateZScore(amount, history);
  
  if (zScore > 2) {
    explanations.push(`Amount is ${zScore.toFixed(1)} standard deviations from normal`);
  }
  
  if (amount > 10000) {
    explanations.push(`High amount: $${amount.toLocaleString()}`);
  }
  
  if (history.length < 3) {
    explanations.push(`New vendor (only ${history.length} historical invoices)`);
  }
  
  if (trustLevel <= 2) {
    explanations.push(`Low trust level (${trustLevel}/5)`);
  }
  
  if (history.length >= 5) {
    const mean = history.reduce((a, b) => a + b, 0) / history.length;
    const variance = history.reduce((sum, val) => sum + Math.pow(val - mean, 2), 0) / history.length;
    const stdDev = Math.sqrt(variance);
    const cv = stdDev / mean;
    
    if (cv > 0.5) {
      explanations.push(`High variance in invoice amounts (${(cv * 100).toFixed(0)}%)`);
    }
  }
  
  return explanations;
}
