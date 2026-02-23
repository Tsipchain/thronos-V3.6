from flask import Flask, Response

from health_check_v3 import health_bp, health_check


AI_CORE_LANDING_HTML = """<!doctype html>
<html lang=\"en\">
  <head>
    <meta charset=\"utf-8\" />
    <title>Thronos AI Core</title>
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <style>
      body { font-family: system-ui, -apple-system, BlinkMacSystemFont, \"Segoe UI\", sans-serif; margin: 0; padding: 0; background: #050816; color: #f9fafb; }
      .hero { min-height: 100vh; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; padding: 2rem; }
      h1 { font-size: clamp(2.5rem, 4vw, 3rem); margin-bottom: 0.75rem; }
      p { max-width: 640px; margin: 0.25rem auto; line-height: 1.6; color: #d1d5db; }
      .tag { display: inline-flex; align-items: center; gap: 0.5rem; padding: 0.3rem 0.75rem; border-radius: 999px; border: 1px solid #4b5563; font-size: 0.8rem; margin-bottom: 1.25rem; color: #9ca3af; }
      .tag-dot { width: 8px; height: 8px; border-radius: 999px; background: #22c55e; box-shadow: 0 0 10px #22c55e; }
      .links { display: flex; flex-wrap: wrap; gap: 0.75rem; justify-content: center; margin-top: 1.75rem; }
      .btn { padding: 0.65rem 1.2rem; border-radius: 999px; border: 1px solid #4b5563; color: #e5e7eb; text-decoration: none; font-size: 0.9rem; transition: background 0.15s ease, border-color 0.15s ease, transform 0.1s ease; }
      .btn.primary { background: linear-gradient(135deg, #22c55e, #38bdf8); border-color: transparent; color: #020617; font-weight: 600; }
      .btn:hover { transform: translateY(-1px); border-color: #9ca3af; }
      .btn.primary:hover { filter: brightness(1.05); }
      .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 1rem; margin-top: 2rem; max-width: 900px; width: 100%; }
      .card { padding: 1rem 1.1rem; border-radius: 0.9rem; border: 1px solid #1f2937; background: radial-gradient(circle at top left, rgba(56,189,248,0.18), transparent 55%), #020617; text-align: left; }
      .card h3 { margin: 0 0 0.3rem; font-size: 0.95rem; }
      .card p { font-size: 0.82rem; margin: 0; color: #9ca3af; }
      .footnote { margin-top: 2rem; font-size: 0.75rem; color: #6b7280; }
    </style>
  </head>
  <body>
    <main class=\"hero\">
      <div class=\"tag\">
        <span class=\"tag-dot\"></span>
        <span>Thronos AI Core · Live</span>
      </div>
      <h1>Autonomous AI Core for Thronos & VerifyID</h1>
      <p>
        This node powers internal AI workloads for the Thronos ecosystem – including VerifyID KYC agents,
        on‑chain copilots, and internal tooling. It is not a public chat interface.
      </p>
      <p>
        Use the documented API endpoints from approved backends to call the AI Core, or contact the
        Thronos team for integration access.
      </p>
      <div class=\"links\">
        <a class=\"btn primary\" href=\"/health\">View live health status</a>
        <a class=\"btn\" href=\"https://thronoschain.org\" target=\"_blank\" rel=\"noreferrer\">thronoschain.org</a>
        <a class=\"btn\" href=\"https://verifyid.thronoschain.org\" target=\"_blank\" rel=\"noreferrer\">VerifyID platform</a>
      </div>
      <section class=\"grid\">
        <article class=\"card\">
          <h3>Internal AI Hub</h3>
          <p>Single AI backend for Thronos apps (Explorer, Governance, Architect, VerifyID assistants).</p>
        </article>
        <article class=\"card\">
          <h3>App‑aware prompts</h3>
          <p>Each client (VerifyID, Architect, Quantum, etc.) gets its own base prompt and safety profile.</p>
        </article>
        <article class=\"card\">
          <h3>On‑chain telemetry</h3>
          <p>Planned support for logging key decisions and rewards into the Thronos chain.</p>
        </article>
      </section>
      <p class=\"footnote\">If you are seeing this page in production, the AI Core node is online and reachable.</p>
    </main>
  </body>
</html>
"""


def create_app() -> Flask:
    app = Flask(__name__)

    # Root landing for ai.thronoschain.org
    @app.route("/", methods=["GET"])
    def landing() -> Response:  # type: ignore[override]
        return Response(AI_CORE_LANDING_HTML, mimetype="text/html")

    # Register health blueprint for AI Core and other nodes
    app.register_blueprint(health_bp)

    # Simple wrapper so /health works (and matches runbook / Render checks)
    @app.route("/health", methods=["GET"])
    def simple_health():  # type: ignore[func-returns-value]
        # Reuse the existing /api/v1/health handler
        return health_check()

    return app


app = create_app()
