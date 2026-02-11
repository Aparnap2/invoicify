import { DurableObject } from 'cloudflare:workers';
import type { Env } from '../db';
import { extractInvoiceWithGroq } from '../lib/groq';
import { calculateRiskScore } from '../lib/risk';
import { generateProcessedKey } from '../lib/storage';

export interface InvoiceMessage {
  traceId: string;
  r2KeyRaw: string;
  vendorId?: string;
  uploadedAt: string;
}

interface ProcessingState {
  status: 'pending' | 'processing' | 'completed' | 'failed';
  startedAt?: number;
  completedAt?: number;
  failedAt?: number;
  error?: string;
  decision?: string;
  r2KeyRaw: string;
}

export class InvoiceProcessor extends DurableObject {
  private env: Env;
  
  constructor(state: DurableObjectState, env: Env) {
    super(state, env);
    this.env = env;
    
    // Resume any in-progress processing after restart
    this.ctx.blockConcurrencyWhile(async () => {
      await this.resumePending();
    });
  }

  // HTTP endpoint for manual triggering/debugging
  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    
    if (url.pathname === '/status') {
      const storage = await this.ctx.storage.list<ProcessingState>({ prefix: 'job:' });
      const jobs = Array.from(storage.entries()).map(([key, value]) => ({
        traceId: key.replace('job:', ''),
        ...value
      }));
      
      return Response.json({
        id: this.ctx.id.toString(),
        pendingJobs: jobs.filter(j => j.status === 'processing').length,
        totalJobs: jobs.length,
        timestamp: new Date().toISOString(),
        jobs
      });
    }
    
    if (url.pathname === '/process' && request.method === 'POST') {
      const body = await request.json<InvoiceMessage>();
      try {
        await this.processInvoice(body);
        return Response.json({ success: true, traceId: body.traceId });
      } catch (error) {
        return Response.json({ 
          success: false, 
          error: (error as Error).message 
        }, { status: 500 });
      }
    }
    
    return new Response('InvoiceProcessor Durable Object', { status: 200 });
  }

  // Queue consumer handler
  async queue(batch: MessageBatch<InvoiceMessage>): Promise<void> {
    console.log(`Processing batch of ${batch.messages.length} messages`);
    
    for (const message of batch.messages) {
      console.log(`Processing message: ${message.body.traceId}, attempt: ${message.attempts}`);
      
      try {
        await this.processInvoice(message.body);
        message.ack();
        console.log(`✅ Completed: ${message.body.traceId}`);
      } catch (error) {
        console.error(`❌ Failed to process invoice ${message.body.traceId}:`, error);
        
        // Retry with exponential backoff
        if (message.attempts < 3) {
          console.log(`🔄 Retrying ${message.body.traceId} (attempt ${message.attempts + 1})`);
          message.retry();
        } else {
          // Move to dead letter queue or manual review
          await this.handleFailedInvoice(message.body, error as Error);
          message.ack();
          console.log(`📋 Sent to failed queue: ${message.body.traceId}`);
        }
      }
    }
  }

  private async processInvoice(message: InvoiceMessage): Promise<void> {
    const { traceId, r2KeyRaw } = message;
    const startTime = Date.now();
    
    // Store processing state
    await this.ctx.storage.put<ProcessingState>(`job:${traceId}`, {
      status: 'processing',
      startedAt: startTime,
      r2KeyRaw
    });

    try {
      // Step 1: Download PDF from R2
      console.log(`📥 Downloading PDF: ${r2KeyRaw}`);
      const pdfBuffer = await this.downloadFromR2(r2KeyRaw);
      
      // Step 2: Extract with Groq Vision
      console.log(`🔍 Extracting with Groq: ${traceId}`);
      const extractedData = await this.extractWithGroq(pdfBuffer, traceId);
      
      // Step 3: Calculate risk score
      console.log(`⚠️ Calculating risk: ${traceId}`);
      const riskScore = await this.calculateRisk(extractedData);
      
      // Step 4: Make decision
      console.log(`🤔 Making decision: ${traceId}`);
      const decision = await this.makeDecision(extractedData, riskScore);
      
      // Step 5: Execute
      if (decision.action === 'AUTO_APPROVE') {
        await this.autoApprove(traceId, extractedData, riskScore);
      } else if (decision.action === 'HITL') {
        await this.sendToHumanReview(traceId, extractedData, riskScore, decision.reasons);
      } else {
        await this.reject(traceId, extractedData, riskScore, decision.reasons);
      }
      
      // Update state
      await this.ctx.storage.put<ProcessingState>(`job:${traceId}`, {
        status: 'completed',
        startedAt: startTime,
        completedAt: Date.now(),
        decision: decision.action,
        r2KeyRaw
      });
      
      const duration = Date.now() - startTime;
      console.log(`✅ Completed ${traceId} in ${duration}ms with decision: ${decision.action}`);
      
    } catch (error) {
      await this.ctx.storage.put<ProcessingState>(`job:${traceId}`, {
        status: 'failed',
        startedAt: startTime,
        failedAt: Date.now(),
        error: (error as Error).message,
        r2KeyRaw
      });
      throw error;
    }
  }

  private async downloadFromR2(key: string): Promise<ArrayBuffer> {
    const object = await this.env.R2_BUCKET.get(key);
    if (!object) {
      throw new Error(`PDF not found in R2: ${key}`);
    }
    return await object.arrayBuffer();
  }

  private async extractWithGroq(pdfBuffer: ArrayBuffer, traceId: string): Promise<any> {
    // Convert to base64
    const base64 = btoa(String.fromCharCode(...new Uint8Array(pdfBuffer)));
    
    // Call Groq API
    const extractedData = await extractInvoiceWithGroq(base64, this.env.GROQ_API_KEY);
    
    // Store extracted result
    const processedKey = generateProcessedKey(traceId);
    await this.env.R2_BUCKET.put(
      processedKey,
      JSON.stringify(extractedData),
      { httpMetadata: { contentType: 'application/json' } }
    );
    
    // Update D1 with extracted data
    await this.updateInvoiceExtraction(traceId, extractedData, processedKey);
    
    return extractedData;
  }

  private async calculateRisk(invoiceData: any): Promise<number> {
    // Query vendor history from D1
    const vendorHistory = await this.getVendorHistory(invoiceData.vendorName);
    
    // Get vendor trust level
    const vendor = await this.getVendor(invoiceData.vendorName);
    
    // Calculate risk
    const riskScore = calculateRiskScore(
      parseFloat(invoiceData.amount),
      vendorHistory.map(h => h.amount),
      vendor?.trustLevel || 1
    );
    
    return riskScore;
  }

  private async makeDecision(
    invoiceData: any, 
    riskScore: number
  ): Promise<{action: string; reasons: string[]}> {
    const reasons: string[] = [];
    const amount = parseFloat(invoiceData.amount);
    
    if (riskScore > 0.7) {
      reasons.push(`High risk score: ${riskScore.toFixed(2)}`);
      return { action: 'REJECT', reasons };
    }
    
    if (riskScore > 0.3) {
      reasons.push(`Medium risk score: ${riskScore.toFixed(2)}`);
      
      if (amount > 10000) {
        reasons.push(`High amount: $${amount.toLocaleString()}`);
      }
      
      return { action: 'HITL', reasons };
    }
    
    if (amount > 5000) {
      reasons.push(`Amount exceeds auto-approve threshold: $${amount.toLocaleString()}`);
      return { action: 'HITL', reasons };
    }
    
    return { action: 'AUTO_APPROVE', reasons: ['Low risk'] };
  }

  private async autoApprove(
    traceId: string, 
    invoiceData: any, 
    riskScore: number
  ): Promise<void> {
    // Update D1 status
    await this.env.DB.prepare(`
      UPDATE invoices 
      SET status = 'APPROVED', 
          risk_score = ?,
          decision = 'AUTO_APPROVED',
          updated_at = datetime('now')
      WHERE id = ?
    `).bind(riskScore, traceId).run();
    
    // TODO: Create QuickBooks bill
    console.log(`✅ Auto-approved invoice ${traceId}`);
  }

  private async sendToHumanReview(
    traceId: string, 
    invoiceData: any, 
    riskScore: number, 
    reasons: string[]
  ): Promise<void> {
    // Update D1 status to HITL
    await this.env.DB.prepare(`
      UPDATE invoices 
      SET status = 'HITL_REQUIRED', 
          risk_score = ?,
          decision_reason = ?,
          updated_at = datetime('now')
      WHERE id = ?
    `).bind(riskScore, JSON.stringify(reasons), traceId).run();
    
    // TODO: Send Slack notification
    console.log(`📋 Sent ${traceId} to human review: ${reasons.join(', ')}`);
  }

  private async reject(
    traceId: string, 
    invoiceData: any, 
    riskScore: number, 
    reasons: string[]
  ): Promise<void> {
    // Update D1 status to REJECTED
    await this.env.DB.prepare(`
      UPDATE invoices 
      SET status = 'REJECTED', 
          risk_score = ?,
          decision_reason = ?,
          updated_at = datetime('now')
      WHERE id = ?
    `).bind(riskScore, JSON.stringify(reasons), traceId).run();
    
    console.log(`❌ Rejected invoice ${traceId}: ${reasons.join(', ')}`);
  }

  private async handleFailedInvoice(message: InvoiceMessage, error: Error): Promise<void> {
    // Update D1 with failure
    await this.env.DB.prepare(`
      UPDATE invoices 
      SET status = 'FAILED', 
          error_message = ?,
          updated_at = datetime('now')
      WHERE id = ?
    `).bind(error.message, message.traceId).run();
    
    // TODO: Send alert to admin
    console.error(`Invoice ${message.traceId} failed permanently:`, error.message);
  }

  private async getVendorHistory(vendorName: string): Promise<any[]> {
    const result = await this.env.DB.prepare(`
      SELECT amount FROM invoices 
      WHERE vendor_name = ? AND status = 'APPROVED'
      ORDER BY created_at DESC 
      LIMIT 20
    `).bind(vendorName).all();
    
    return result.results || [];
  }

  private async getVendor(vendorName: string): Promise<any> {
    const result = await this.env.DB.prepare(`
      SELECT * FROM vendors 
      WHERE name = ?
    `).bind(vendorName).first();
    
    return result;
  }

  private async updateInvoiceExtraction(
    traceId: string, 
    extractedData: any,
    processedKey: string
  ): Promise<void> {
    await this.env.DB.prepare(`
      UPDATE invoices 
      SET vendor_name = ?,
          invoice_number = ?,
          amount = ?,
          currency = ?,
          invoice_date = ?,
          due_date = ?,
          r2_key_processed = ?,
          status = 'EXTRACTED',
          updated_at = datetime('now')
      WHERE id = ?
    `).bind(
      extractedData.vendorName,
      extractedData.invoiceNumber,
      extractedData.amount,
      extractedData.currency,
      extractedData.invoiceDate,
      extractedData.dueDate,
      processedKey,
      traceId
    ).run();
  }

  private async resumePending(): Promise<void> {
    // Check for any jobs that were processing before restart
    const jobs = await this.ctx.storage.list<ProcessingState>({ prefix: 'job:' });
    for (const [key, value] of jobs) {
      if (value.status === 'processing') {
        const traceId = key.replace('job:', '');
        console.log(`🔄 Resuming job: ${traceId}`);
        
        // Re-process the invoice
        try {
          await this.processInvoice({
            traceId,
            r2KeyRaw: value.r2KeyRaw,
            uploadedAt: new Date(value.startedAt || Date.now()).toISOString()
          });
        } catch (error) {
          console.error(`Failed to resume ${traceId}:`, error);
        }
      }
    }
  }
}
