"use client";

/** Last resort when the root layout itself fails: plain HTML, no app styles needed. */
export default function GlobalError({ reset }: { error: Error; reset: () => void }) {
  return (
    <html lang="en">
      <body style={{ fontFamily: "system-ui, sans-serif", background: "#fbfaf7", color: "#16213a", padding: 32 }}>
        <h1 style={{ fontSize: 22 }}>Twin couldn&apos;t load</h1>
        <p style={{ color: "#5a6170" }}>Please reload the page. Your data is safe.</p>
        <button
          onClick={reset}
          style={{ marginTop: 12, padding: "8px 16px", borderRadius: 6, border: 0, background: "#be400e", color: "#fff", fontWeight: 600 }}
        >
          Try again
        </button>
      </body>
    </html>
  );
}
