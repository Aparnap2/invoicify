import axios from "axios"
import type { AxiosInstance } from "axios"

const AI_SERVICE_URL = process.env.NEXT_PUBLIC_AI_SERVICE_URL || "http://localhost:8001"

export const aiClient: AxiosInstance = axios.create({
  baseURL: AI_SERVICE_URL,
  headers: {
    "Content-Type": "application/json",
  },
})

// Types for AI service responses
export interface ExtractionResponse {
  success: boolean
  invoice_id?: string
  data?: {
    vendor_name: string
    invoice_number: string
    invoice_date: string
    due_date: string
    total_amount: number
    currency: string
    line_items?: Array<{
      line_number: number
      description: string
      quantity: number
      unit_price: number
      amount: number
    }>
  }
  confidence: number
  notes: string[]
  error?: string
}

export interface ProcessingResponse {
  success: boolean
  thread_id: string
  result?: {
    invoice_id: string
    status: string
    requires_approval: boolean
    error_message?: string
  }
  error?: string
}

export async function extractInvoice(rawContent: string): Promise<ExtractionResponse> {
  const response = await aiClient.post<ExtractionResponse>("/api/v1/extract", {
    raw_content: rawContent,
    source_file_name: "uploaded_invoice.txt",
    source_file_type: "txt",
  })
  return response.data
}

export async function processInvoice(rawContent: string): Promise<ProcessingResponse> {
  const response = await aiClient.post<ProcessingResponse>("/api/v1/process", {
    raw_content: rawContent,
    source_file_name: "uploaded_invoice.txt",
    source_file_type: "txt",
  })
  return response.data
}

export async function submitApproval(
  threadId: string,
  action: "approve" | "reject",
  approverEmail: string,
  approverId: string,
  comments?: string
): Promise<ProcessingResponse> {
  const response = await aiClient.post<ProcessingResponse>("/api/v1/approve", {
    thread_id: threadId,
    action,
    approver_email: approverEmail,
    approver_id: approverId,
    comments,
  })
  return response.data
}

export async function checkStatus(threadId: string): Promise<{ status: string }> {
  const response = await aiClient.get<{ status: string }>(`/api/v1/status/${threadId}`)
  return response.data
}
