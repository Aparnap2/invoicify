import type { Env } from "../db";

/**
 * Invoice extraction result from Llama Vision
 */
export interface InvoiceExtractionResult {
  success: boolean;
  data?: ExtractedInvoiceData;
  error?: string;
  confidence: number;
  processingTime: number;
}

/**
 * Extracted invoice data structure
 */
export interface ExtractedInvoiceData {
  vendorName: string;
  vendorAddress?: string;
  vendorPhone?: string;
  vendorEmail?: string;
  invoiceNumber: string;
  invoiceDate?: string;
  dueDate?: string;
  totalAmount: number;
  subtotal?: number;
  tax?: number;
  currency: string;
  paymentTerms?: string;
  lineItems: LineItem[];
  notes?: string;
}

/**
 * Line item extracted from invoice
 */
export interface LineItem {
  description: string;
  quantity: number;
  unitPrice: number;
  amount: number;
  glCode?: string;
}

/**
 * System prompt for Llama Vision to extract invoice data
 */
const EXTRACTION_PROMPT = `You are an expert invoice data extraction system. Extract all invoice information from the provided document image and return a JSON object with the following structure:

{
  "vendorName": "Full vendor/company name",
  "vendorAddress": "Full vendor address if visible",
  "vendorPhone": "Vendor phone number if visible",
  "vendorEmail": "Vendor email if visible",
  "invoiceNumber": "Invoice number",
  "invoiceDate": "Invoice date in YYYY-MM-DD format",
  "dueDate": "Due date in YYYY-MM-DD format",
  "totalAmount": "Total amount as a number",
  "subtotal": "Subtotal amount as a number if shown",
  "tax": "Tax amount as a number if shown",
  "currency": "Currency code (USD, EUR, GBP, etc.)",
  "paymentTerms": "Payment terms if specified",
  "lineItems": [
    {
      "description": "Item description",
      "quantity": "Quantity as a number",
      "unitPrice": "Unit price as a number",
      "amount": "Line amount as a number"
    }
  ],
  "notes": "Any additional notes or special instructions"
}

CRITICAL RULES:
1. Extract ALL visible line items with their descriptions, quantities, unit prices, and amounts
2. Calculate the total amount - it should equal the sum of all line items (plus tax if applicable)
3. Use YYYY-MM-DD format for all dates. If date format is unclear, infer from context
4. Currency: Use the symbol or code shown ($, USD, €, EUR, £, GBP, etc.)
5. If any field is not visible or cannot be determined, use null
6. Return ONLY valid JSON, no markdown code blocks, no explanations
7. Be precise with numbers - don't round unless the original shows rounded values
8. Extract the vendor name from letterhead, logos, or the "From:" section
9. Extract customer/buyer info from the "To:" section if visible
10. Look for payment details like bank account, routing number, IBAN if visible

Return the extracted data as a raw JSON object only.`;

/**
 * Extract invoice data from an image using Llama Vision
 */
export async function extractInvoiceWithVision(
  env: Env,
  imageBase64: string,
  mimeType: string = "image/jpeg"
): Promise<InvoiceExtractionResult> {
  const startTime = Date.now();

  try {
    // Call Workers AI with Llama Vision model
    const response = await env.AI.run("@cf/meta/llama-3.2-11b-vision-instruct", {
      messages: [
        {
          role: "user",
          content: [
            { type: "text", text: EXTRACTION_PROMPT },
            {
              type: "image_url",
              image_url: {
                url: `data:${mimeType};base64,${imageBase64}`,
              },
            },
          ],
        },
      ],
      max_tokens: 2000,
      temperature: 0.1,
    });

    const processingTime = Date.now() - startTime;

    // Parse the JSON response
    let extractedData: ExtractedInvoiceData;

    try {
      // Handle different response formats from Workers AI
      const responseText =
        typeof response === "string"
          ? response
          : response.completion || response.response || JSON.stringify(response);

      // Clean up response if it has markdown code blocks
      const cleanedText = responseText
        .replace(/```json/g, "")
        .replace(/```/g, "")
        .trim();

      extractedData = JSON.parse(cleanedText);
    } catch (parseError) {
      return {
        success: false,
        error: `Failed to parse AI response: ${parseError}`,
        confidence: 0,
        processingTime: Date.now() - startTime,
      };
    }

    // Validate required fields
    if (!extractedData.vendorName || !extractedData.invoiceNumber) {
      return {
        success: false,
        error: "Missing required fields: vendorName and invoiceNumber",
        confidence: 0,
        processingTime,
      };
    }

    // Validate line items
    if (!Array.isArray(extractedData.lineItems) || extractedData.lineItems.length === 0) {
      return {
        success: false,
        error: "No line items found in invoice",
        confidence: 0,
        processingTime,
      };
    }

    // Calculate confidence based on data completeness
    const confidence = calculateConfidence(extractedData);

    return {
      success: true,
      data: extractedData,
      confidence,
      processingTime,
    };
  } catch (error) {
    return {
      success: false,
      error: `Vision extraction failed: ${error}`,
      confidence: 0,
      processingTime: Date.now() - startTime,
    };
  }
}

/**
 * Calculate confidence score based on data completeness
 */
function calculateConfidence(data: ExtractedInvoiceData): number {
  const requiredFields = [
    data.vendorName,
    data.invoiceNumber,
    data.totalAmount,
    data.currency,
  ];

  const optionalFields = [
    data.vendorAddress,
    data.vendorEmail,
    data.invoiceDate,
    data.dueDate,
    data.tax,
    data.subtotal,
  ];

  const lineItemsComplete = data.lineItems.every(
    (item) => item.description && item.quantity && item.unitPrice && item.amount
  );

  const requiredScore = requiredFields.every(Boolean) ? 0.6 : 0;
  const optionalScore = optionalFields.filter(Boolean).length / optionalFields.length * 0.2;
  const lineItemsScoreValue = lineItemsComplete && data.lineItems.length > 0 ? 0.2 : 0;

  return Math.min(requiredScore + optionalScore + lineItemsScoreValue, 1);
}

/**
 * Extract text from image and return raw response for debugging
 */
export async function extractRawText(
  env: Env,
  imageBase64: string,
  mimeType: string = "image/jpeg"
): Promise<string> {
  const response = await env.AI.run("@cf/meta/llama-3.2-11b-vision-instruct", {
    messages: [
      {
        role: "user",
        content: [
          {
            type: "text",
            text: "Extract all visible text from this invoice image. Preserve the structure and layout as much as possible.",
          },
          {
            type: "image_url",
            image_url: {
              url: `data:${mimeType};base64,${imageBase64}`,
            },
          },
        ],
      },
    ],
    max_tokens: 4000,
  });

  return typeof response === "string"
    ? response
    : response.completion || response.response || JSON.stringify(response);
}
