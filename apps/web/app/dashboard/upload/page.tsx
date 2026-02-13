"use client"

import { useState, useCallback } from "react"
import { useRouter } from "next/navigation"
import { Upload, FileText, X, CheckCircle, AlertCircle, Loader2 } from "lucide-react"
import { processInvoice } from "@/lib/ai-client"
import { cn } from "@/lib/utils"

export default function UploadPage() {
  const router = useRouter()
  const [dragActive, setDragActive] = useState(false)
  const [files, setFiles] = useState<File[]>([])
  const [processing, setProcessing] = useState(false)
  const [results, setResults] = useState<{
    success: boolean
    vendorName?: string
    invoiceNumber?: string
    totalAmount?: number
    confidence?: number
    error?: string
  } | null>(null)

  const handleDrag = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true)
    } else if (e.type === "dragleave") {
      setDragActive(false)
    }
  }, [])

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setDragActive(false)

    const droppedFiles = Array.from(e.dataTransfer.files).filter(
      (file) => file.type === "application/pdf" || file.type.startsWith("image/")
    )
    setFiles(droppedFiles)
    setResults(null)
  }, [])

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFiles = Array.from(e.target.files || []).filter(
      (file) => file.type === "application/pdf" || file.type.startsWith("image/")
    )
    setFiles(selectedFiles)
    setResults(null)
  }

  const removeFile = () => {
    setFiles([])
    setResults(null)
  }

  async function handleProcess() {
    if (files.length === 0) return

    setProcessing(true)
    setResults(null)

    try {
      // Read file content
      const file = files[0]
      const textContent = await readFileAsText(file)

      // Process with AI service
      const result = await processInvoice(textContent)

      if (result.success) {
        setResults({
          success: true,
          vendorName: result.result?.invoice_id, // Would be populated from actual response
          confidence: result.success ? 0.85 : undefined,
        })

        // Redirect to invoices page after short delay
        setTimeout(() => {
          router.push("/dashboard/invoices")
        }, 2000)
      } else {
        setResults({
          success: false,
          error: result.error || "Processing failed",
        })
      }
    } catch (error) {
      console.error("Processing error:", error)
      setResults({
        success: false,
        error: error instanceof Error ? error.message : "Processing failed",
      })
    } finally {
      setProcessing(false)
    }
  }

  async function readFileAsText(file: File): Promise<string> {
    return new Promise((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = () => resolve(reader.result as string)
      reader.onerror = reject
      reader.readAsText(file)
    })
  }

  return (
    <div className="max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Upload Invoice</h1>
        <p className="text-gray-600">
          Upload an invoice PDF or image for AI-powered extraction
        </p>
      </div>

      {/* Upload Zone */}
      <div
        className={cn(
          "relative rounded-lg border-2 border-dashed p-12 text-center transition-colors",
          dragActive
            ? "border-blue-500 bg-blue-50"
            : "border-gray-300 hover:border-gray-400"
        )}
        onDragEnter={handleDrag}
        onDragLeave={handleDrag}
        onDragOver={handleDrag}
        onDrop={handleDrop}
      >
        <input
          type="file"
          accept=".pdf,.png,.jpg,.jpeg"
          onChange={handleFileChange}
          className="absolute inset-0 cursor-pointer opacity-0"
          disabled={processing}
        />

        {files.length > 0 ? (
          <div className="flex items-center justify-center gap-4">
            <FileText className="h-12 w-12 text-blue-600" />
            <div className="text-left">
              <p className="font-medium text-gray-900">{files[0].name}</p>
              <p className="text-sm text-gray-600">
                {(files[0].size / 1024).toFixed(1)} KB
              </p>
            </div>
            {!processing && (
              <button
                onClick={removeFile}
                className="rounded-full p-2 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
              >
                <X className="h-5 w-5" />
              </button>
            )}
          </div>
        ) : (
          <div className="space-y-4">
            <div className="flex justify-center">
              <Upload className="h-12 w-12 text-gray-400" />
            </div>
            <div>
              <p className="text-lg font-medium text-gray-900">
                Drop your invoice here
              </p>
              <p className="text-sm text-gray-600">
                or click to browse (PDF, PNG, JPG)
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Processing Status */}
      {processing && (
        <div className="rounded-lg bg-blue-50 p-4">
          <div className="flex items-center gap-3">
            <Loader2 className="h-5 w-5 animate-spin text-blue-600" />
            <p className="font-medium text-blue-700">Processing invoice...</p>
          </div>
          <p className="mt-2 text-sm text-blue-600">
            Our AI is extracting data from your invoice. This may take a moment.
          </p>
        </div>
      )}

      {/* Results */}
      {results && (
        <div
          className={cn(
            "rounded-lg p-4",
            results.success ? "bg-green-50" : "bg-red-50"
          )}
        >
          <div className="flex items-start gap-3">
            {results.success ? (
              <CheckCircle className="h-5 w-5 text-green-600" />
            ) : (
              <AlertCircle className="h-5 w-5 text-red-600" />
            )}
            <div>
              <p
                className={cn(
                  "font-medium",
                  results.success ? "text-green-700" : "text-red-700"
                )}
              >
                {results.success
                  ? "Invoice processed successfully!"
                  : "Processing failed"}
              </p>
              {results.success && (
                <p className="mt-1 text-sm text-green-600">
                  Redirecting to invoices...
                </p>
              )}
              {results.error && (
                <p className="mt-1 text-sm text-red-600">{results.error}</p>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Process Button */}
      {files.length > 0 && !processing && !results && (
        <div className="flex justify-end">
          <button
            onClick={handleProcess}
            className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-6 py-3 font-medium text-white hover:bg-blue-700"
          >
            <Upload className="h-5 w-5" />
            Process Invoice
          </button>
        </div>
      )}

      {/* Tips */}
      <div className="rounded-lg bg-gray-50 p-4">
        <h3 className="font-medium text-gray-900">Tips for best results:</h3>
        <ul className="mt-2 space-y-1 text-sm text-gray-600">
          <li>- Use high-quality, legible invoices</li>
          <li>- Ensure all text is visible and not obscured</li>
          <li>- Include clear line items and totals</li>
          <li>- Multi-page invoices work best as PDFs</li>
        </ul>
      </div>
    </div>
  )
}
