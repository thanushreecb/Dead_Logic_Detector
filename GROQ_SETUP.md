# How to Use Groq API with Dead Logic Detector

## Step-by-Step Setup

### 1. Create Groq Account
- Go to [Groq Console](https://console.groq.com)
- Sign up (free account)
- Verify your email

### 2. Get API Key
- Log in to Groq Console
- Navigate to **API Keys** section
- Click **Create New API Key**
- Copy the key
- Save it somewhere safe

### 3. Set Environment Variable (Windows PowerShell)

```powershell
$env:GROQ_API_KEY = "gsk_your_actual_key_here"
```

Verify it's set:
```powershell
$env:GROQ_API_KEY
```

### 4. Install Groq Package (if not already installed)

```powershell
python -m pip install groq
```

### 5. Run the Detector

```powershell
cd c:\Users\Srivishnu\Downloads\LLM_DC_SA_IB\LLM_DC_SA_IB
python pipeline.py sample_target.py
```

## API Provider Priority

The detector checks for API keys in this order:
1. `GROQ_API_KEY` (fastest, free tier is generous)
2. `GEMINI_API_KEY` (slower, free tier limited)
3. `ANTHROPIC_API_KEY` (paid only)

**Set only ONE** to avoid confusion.

## Groq API Models Available

The detector uses **`mixtral-8x7b-32768`** model which is:
- ✅ Fast (great for local dev)
- ✅ Free tier: 30 requests/min
- ✅ Generous usage limits
- ✅ Good quality for code analysis

## Run Benchmarks with Groq

```powershell
python benchmark.py
```

This will test all sample files using Groq for faster analysis.

## Troubleshooting

### API Key Not Recognized
```powershell
# Windows PowerShell - Make sure you use THIS format:
$env:GROQ_API_KEY = "your_key"

# Verify
echo $env:GROQ_API_KEY
```

### Rate Limit Errors
- Free tier: 30 requests/min, 14,400/day
- Wait a minute and retry
- Upgrade to paid for higher limits

### Connection Issues
- Check internet connection
- Verify API key is correct
- Visit [Groq Status](https://status.groq.com) to check service health

## Compare Providers

| Provider   | Speed | Free Tier | Quality |
|-----------|-------|-----------|---------|
| **Groq**   | 🔥 Fastest | 30 req/min | Good |
| Gemini    | ⚡ Fast | Limited quota | Good |
| Anthropic | ⏱️  Slowest | ❌ None | Excellent |

**Recommendation**: Use Groq for development, Gemini for CI/CD (if quota available).

## Using Multiple Detectors

To run multiple analyses, unset the API key temporarily:
```powershell
$env:GROQ_API_KEY = ""
python pipeline.py sample_target.py  # Heuristic mode only, no API
```

Results will still be generated but without LLM reasoning.
