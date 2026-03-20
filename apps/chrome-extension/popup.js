/**
 * Shinbee AI Navigator — Popup Logic
 */

const messagesEl = document.getElementById('chat-messages');
const inputEl = document.getElementById('message-input');
const sendBtn = document.getElementById('send-btn');
const voiceBtn = document.getElementById('voice-btn');
const clearBtn = document.getElementById('clear-btn');
const statusEl = document.getElementById('status');

let conversationHistory = [];
let isProcessing = false;
let recognition = null;
let isRecording = false;

// --- UI Helpers ---

function addMessage(text, type) {
  const div = document.createElement('div');
  div.className = `msg msg-${type}`;
  div.textContent = text;
  messagesEl.appendChild(div);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function addActionMessage(text) {
  const div = document.createElement('div');
  div.className = 'msg msg-action';
  div.textContent = text;
  messagesEl.appendChild(div);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function setStatus(text, isError = false) {
  statusEl.textContent = text;
  statusEl.className = isError ? 'status error' : 'status';
}

function setProcessing(processing) {
  isProcessing = processing;
  sendBtn.disabled = processing;
  inputEl.disabled = processing;
  if (processing) {
    setStatus('AI が分析中...');
    sendBtn.textContent = '...';
  } else {
    setStatus('');
    sendBtn.textContent = '送信';
  }
}

// --- Send Message ---

async function sendMessage() {
  const message = inputEl.value.trim();
  if (!message || isProcessing) return;

  inputEl.value = '';
  addMessage(message, 'user');
  setProcessing(true);

  try {
    const result = await chrome.runtime.sendMessage({
      type: 'navigate-query',
      message,
      history: conversationHistory,
    });

    if (result.error) {
      addMessage(`Error: ${result.error}`, 'ai');
      setStatus(result.error, true);
    } else {
      // Show AI response
      addMessage(result.response_text, 'ai');

      // Show action summaries
      if (result.actions?.length > 0) {
        for (const action of result.actions) {
          const desc = describeAction(action);
          if (desc) addActionMessage(desc);
        }
      }

      // Update conversation history
      conversationHistory.push(
        { role: 'user', text: message },
        { role: 'model', text: result.response_text },
      );

      // Keep last 10 turns
      if (conversationHistory.length > 20) {
        conversationHistory = conversationHistory.slice(-20);
      }
    }
  } catch (err) {
    addMessage(`Error: ${err.message}`, 'ai');
    setStatus(err.message, true);
  } finally {
    setProcessing(false);
  }
}

function describeAction(action) {
  switch (action.type) {
    case 'navigate':
      return `→ ページ移動: ${action.url}`;
    case 'highlight':
      return `→ ハイライト: ${action.label || action.selector}`;
    case 'click':
      return `→ クリック: ${action.selector}`;
    case 'scroll':
      return `→ スクロール: ${action.selector}`;
    default:
      return null;
  }
}

// --- Voice Input (Web Speech API) ---

function initVoiceRecognition() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    voiceBtn.style.display = 'none';
    return;
  }

  recognition = new SpeechRecognition();
  recognition.lang = 'ja-JP';
  recognition.continuous = false;
  recognition.interimResults = true;

  recognition.onresult = (event) => {
    let transcript = '';
    for (const result of event.results) {
      transcript += result[0].transcript;
    }
    inputEl.value = transcript;
  };

  recognition.onend = () => {
    isRecording = false;
    voiceBtn.classList.remove('recording');
    // Auto-send if there's text
    if (inputEl.value.trim()) {
      sendMessage();
    }
  };

  recognition.onerror = (event) => {
    isRecording = false;
    voiceBtn.classList.remove('recording');
    if (event.error !== 'no-speech') {
      setStatus(`音声認識エラー: ${event.error}`, true);
    }
  };
}

function toggleVoice() {
  if (!recognition) {
    setStatus('音声認識は利用できません', true);
    return;
  }

  if (isRecording) {
    recognition.stop();
    isRecording = false;
    voiceBtn.classList.remove('recording');
  } else {
    inputEl.value = '';
    recognition.start();
    isRecording = true;
    voiceBtn.classList.add('recording');
    setStatus('音声入力中...');
  }
}

// --- Event Listeners ---

sendBtn.addEventListener('click', sendMessage);

inputEl.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

voiceBtn.addEventListener('click', toggleVoice);

clearBtn.addEventListener('click', () => {
  chrome.runtime.sendMessage({ type: 'clear-highlights' });
  setStatus('ハイライトを消去しました');
});

// Init
initVoiceRecognition();
