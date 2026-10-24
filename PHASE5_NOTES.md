# RouteNex - Phase 5 (free AI assistant)

## Apply
Copy over your project (keep `frontend/assets/`, `database/seed.py`, `.env`):
`backend/` (whole folder), `frontend/` (all files), `database/schema.sql`. Start with `start.bat`; press Ctrl+Shift+R once.
Tests: `pytest backend\tests -q`. A chat bubble appears bottom-right for every role.

## It works with NO setup (built-in engine). To add a real language model (all free):
**Option A - Local model with Ollama (recommended: private, nothing leaves your laptop)**
1. `winget install Ollama.Ollama`  (then close and reopen Command Prompt)
2. `ollama pull qwen2.5:3b`   (about 2 GB download, needs about 4 GB free RAM). Low RAM? `ollama pull qwen2.5:1.5b` and add `OLLAMA_MODEL=qwen2.5:1.5b` to `backend\.env`.
3. Restart `start.bat`. The assistant header changes from "built-in engine" to `ollama:qwen2.5:3b`.
**Option B - Gemini free tier (cloud)**
1. Create a free key at aistudio.google.com (no card). 2. Add `GEMINI_API_KEY=your-key` to `backend\.env`. 3. Restart.
   Google's free tier may use inputs to improve its products, so phone numbers/emails are stripped before sending, and you should not use it with real customer data. If the model name is retired the app auto-picks a current Flash model.

## How it stays safe
- The model only picks a tool (strict JSON, allow-list per role) and phrases narrative answers. Prices, balances and statuses always come from code.
- Booking, cancelling, applying a route plan and reporting a breakdown are only PROPOSED. They run when you press Confirm (each proposal belongs to one user, expires in 10 min, runs once).
- Roles are enforced server-side: a customer cannot reach operations tools even if the model is tricked.
- If the model is down, slow, rate-limited or answers badly, the built-in engine takes over automatically.
- Rate limit: 20 messages/min per user.

## Try these
Customer: "cab from C-Scheme to the airport pay with wallet" -> Confirm -> Track. "send a parcel from Malviya Nagar to Amer Fort 2kg" then "Ravi 9876543210". "how do I cancel a ride?" "what offers do I have?"
Driver: "what's my next stop?" "where is demand coming?"
Dispatcher/admin: "give me the report", "which stops are at risk?", "preview the route plan" -> Confirm, "RJ14-RN-203 broke down", "why is order 28 late?"

## Be upfront in the viva
- Tested here with a scripted stand-in for the model (routing, composing, injection, fallback, privacy); I could not run Ollama or Gemini in my sandbox, so please try your chosen model and tell me what you see. Small local models can mis-route; that is why every answer with numbers is deterministic and every change needs your confirmation.
- Voice input uses the browser's speech recognition (Chrome on Android works). The built-in engine understands English; a real model also handles Hindi.
