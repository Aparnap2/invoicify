import type { ExtractedInvoice } from '../types';

interface GroqRequest {
  model: string;
  messages: Array<{
    role: string;
    content: Array<{ type: string; text?: string; image_url?: { url: string } }>;
  }>;
  response_format?: { type: string };
  temperature?: number;
}

interface GroqResponse {
  choices: Array<{
    message: {
      content: string;
    };
  }>;
}

export async function extractInvoiceWithGroq(
  pdfBase64: string,
  apiKey: string
): Promise<ExtractedInvoice> {
  const response = await fetch('https://api.groq.com/openai/v1/chat/completions', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${apiKey}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      model: 'llama-3.2-90b-vision-preview',
      messages: [{
        role: 'user',
        content: [
          {
            type: 'text',
            text: `Extract invoice data as JSON with this exact structure:
{
  "vendorName": "string",
  "invoiceNumber": "string", 
  "amount": number,
  "currency": "USD",
  "invoiceDate": "YYYY-MM-DD",
  "dueDate": "YYYY-MM-DD",
  "lineItems": [
    {
      "description": "string",
      "quantity": number,
      "unitPrice": number,
      "total": number
    }
  ],
  "confidence": 0.95
}
Extract all visible information from the invoice. Use ISO date format. Set confidence based on clarity of extraction.`
          },
          {
            type: 'image_url',
            image_url: {
              url: `data:application/pdf;base64,${pdfBase64}`
            }
          }
        ]
      }],
      response_format: { type: 'json_object' },
      temperature: 0.1
    } as GroqRequest)
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Groq API error (${response.status}): ${errorText}`);
  }

  const data = await response.json() as GroqResponse;
  
  if (!data.choices || data.choices.length === 0) {
    throw new Error('Groq API returned no choices');
  }

  const content = data.choices[0].message.content;
  
  try {
    const parsed = JSON.parse(content) as ExtractedInvoice;
    
    // Validate required fields
    if (!parsed.vendorName || !parsed.invoiceNumber || typeof parsed.amount !== 'number') {
      throw new Error('Missing required fields in extracted data');
    }
    
    return parsed;
  } catch (parseError) {
    throw new Error(`Failed to parse Groq response: ${parseError}. Content: ${content.substring(0, 200)}`);
  }
}

// Alternative: Local Ollama for development/testing
export async function extractInvoiceWithOllama(
  pdfBase64: string,
  ollamaUrl: string = 'http://localhost:11434',
  model: string = 'llava'
): Promise<ExtractedInvoice> {
  const response = await fetch(`${ollamaUrl}/api/generate`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      model,
      prompt: `Extract invoice data from this image as JSON: {"vendorName": "", "invoiceNumber": "", "amount": 0, "currency": "USD", "invoiceDate": "YYYY-MM-DD", "lineItems": []}`,
      images: [pdfBase64],
      stream: false
    })
  });

  if (!response.ok) {
    throw new Error(`Ollama API error: ${response.statusText}`);
  }

  const data = await response.json();
  
  // Parse the response text as JSON
  try {
    const parsed = JSON.parse(data.response) as ExtractedInvoice;
    return parsed;
  } catch {
    // If not valid JSON, return structured error
    throw new Error(`Ollama returned non-JSON response: ${data.response}`);
  }
}

// Factory to choose between Groq and Ollama
export function createExtractor(
  config: { type: 'groq'; apiKey: string } | { type: 'ollama'; url: string; model: string }
) {
  if (config.type === 'groq') {
    return (pdfBase64: string) => extractInvoiceWithGroq(pdfBase64, config.apiKey);
  } else {
    return (pdfBase64: string) => extractInvoiceWithOllama(pdfBase64, config.url, config.model);
  }
}
