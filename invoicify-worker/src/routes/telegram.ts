/**
 * Telegram Webhook Route
 * 
 * Receives invoice PDFs from vendors via Telegram Bot API
 * Forwards to Agent Core MCP server for processing
 * 
 * Cost: $0 forever (Telegram Bot API is free unlimited)
 */

import { Hono } from 'hono'
import { HTTPException } from 'hono/http-exception'

export const telegram = new Hono()

// Telegram bot configuration
const BOT_TOKEN = Deno.env.get('TELEGRAM_BOT_TOKEN')
const AGENT_CORE_URL = Deno.env.get('AGENT_CORE_BASE_URL') || 'http://host.docker.internal:8001'

/**
 * POST /webhook/telegram
 * 
 * Telegram sends updates to this webhook when:
 * - User sends a message
 * - User sends a document (invoice PDF)
 * - User interacts with bot
 */
telegram.post('/webhook/telegram', async (c) => {
  const update = await c.req.json()
  
  // Log update for debugging
  console.log('Telegram webhook received:', JSON.stringify(update, null, 2))
  
  // Handle document messages (invoice PDFs)
  if (update.message?.document) {
    try {
      const { file_id, file_name, chat } = update.message.document
      const chatId = chat.id.toString()
      const username = chat.username || chat.first_name || 'unknown'
      
      console.log(`📄 Invoice PDF received from @${username}: ${file_name}`)
      
      // Send immediate acknowledgment
      await sendTelegramMessage(chatId, 
        `⏳ Processing invoice: ${file_name}\n\n` +
        `Please wait while I extract the data...`
      )
      
      // Call Agent Core MCP server to process invoice
      const mcpResponse = await fetch(`${AGENT_CORE_URL}/mcp/call_tool`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          tool_name: 'telegram_receive_invoice',
          arguments: {
            file_id,
            chat_id: chatId,
            sender_username: username,
          },
        }),
      })
      
      if (!mcpResponse.ok) {
        throw new Error(`Agent Core returned ${mcpResponse.status}`)
      }
      
      const result = await mcpResponse.json()
      
      console.log(`✅ Invoice processed: trace_id=${result.trace_id}`)
      
      return c.json({ 
        status: 'success', 
        trace_id: result.trace_id,
        invoice_number: result.invoice_number,
      })
      
    } catch (error) {
      console.error('Error processing Telegram invoice:', error)
      
      // Send error message to user
      const chatId = update.message.chat.id.toString()
      await sendTelegramMessage(chatId,
        `❌ Error processing invoice\n\n` +
        `Please try again or contact support.`
      )
      
      return c.json({ status: 'error', error: error.message }, 500)
    }
  }
  
  // Handle text messages (commands)
  if (update.message?.text) {
    const text = update.message.text
    const chatId = update.message.chat.id.toString()
    
    if (text === '/start') {
      await sendTelegramMessage(chatId,
        `👋 Welcome to Invoicify Bot!\n\n` +
        `📤 *How to submit an invoice:*\n` +
        `1. Forward any invoice PDF to this chat\n` +
        `2. I'll process it automatically\n` +
        `3. You'll get a confirmation when done\n\n` +
        `⚡ *Processing time:* ~30 seconds\n` +
        `💰 *Cost:* Free forever!`
      )
    } else if (text === '/help') {
      await sendTelegramMessage(chatId,
        `📖 *Invoicify Bot Help*\n\n` +
        `*Commands:*\n` +
        `/start - Start invoice processing\n` +
        `/help - Show this help message\n` +
        `/status <trace_id> - Check invoice status\n\n` +
        `*Supported formats:*\n` +
        `• PDF invoices\n` +
        `• Any vendor\n` +
        `• Any amount\n\n` +
        `*Need help?* Contact support`
      )
    } else {
      await sendTelegramMessage(chatId,
        `❓ Unknown command: ${text}\n\n` +
        `Use /start to begin or /help for assistance.`
      )
    }
    
    return c.json({ status: 'handled' })
  }
  
  // Ignore other update types (callback queries, etc.)
  return c.json({ status: 'ignored' })
})

/**
 * GET /webhook/telegram/health
 * 
 * Health check endpoint for monitoring
 */
telegram.get('/webhook/telegram/health', (c) => {
  return c.json({
    status: 'healthy',
    bot_configured: !!BOT_TOKEN,
    agent_core_url: AGENT_CORE_URL,
    timestamp: new Date().toISOString(),
  })
})

/**
 * Send message to Telegram chat
 */
async function sendTelegramMessage(chatId: string, text: string, parseMode: 'Markdown' | 'HTML' = 'Markdown') {
  if (!BOT_TOKEN) {
    console.error('TELEGRAM_BOT_TOKEN not configured')
    return
  }
  
  try {
    const response = await fetch(`https://api.telegram.org/bot${BOT_TOKEN}/sendMessage`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        chat_id: chatId,
        text,
        parse_mode: parseMode,
      }),
    })
    
    if (!response.ok) {
      throw new Error(`Telegram API returned ${response.status}`)
    }
    
    const result = await response.json()
    console.log(`📤 Message sent to ${chatId}: message_id=${result.result.message_id}`)
    
    return result
  } catch (error) {
    console.error('Error sending Telegram message:', error)
    throw error
  }
}

/**
 * Set webhook on Telegram servers (call once during deployment)
 * 
 * Usage: curl https://your-worker.azurecontainerapps.io/webhook/telegram/set-webhook
 */
telegram.get('/webhook/telegram/set-webhook', async (c) => {
  if (!BOT_TOKEN) {
    throw new HTTPException(400, { message: 'TELEGRAM_BOT_TOKEN not configured' })
  }
  
  const webhookUrl = `${c.req.url.replace('/webhook/telegram/set-webhook', '/webhook/telegram')}`
  
  const response = await fetch(`https://api.telegram.org/bot${BOT_TOKEN}/setWebhook`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      url: webhookUrl,
      allowed_updates: ['message', 'callback_query'],
    }),
  })
  
  if (!response.ok) {
    throw new HTTPException(500, { message: `Telegram API error: ${response.status}` })
  }
  
  const result = await response.json()
  
  return c.json({
    status: 'success',
    webhook_url: webhookUrl,
    telegram_response: result,
  })
})
