"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import Nav from "@/components/Nav";
import { useAuthGuard } from "@/lib/useAuthGuard";
import { createJob, getShortcodes } from "@/lib/api-client";
import type { Shortcode } from "@/lib/auth";

export default function ExtractPage() {
  const { user, loading } = useAuthGuard();
  const router = useRouter();
  const [shortcodes, setShortcodes] = useState<Shortcode[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [destinations, setDestinations] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (user) getShortcodes().then(setShortcodes).catch(() => {});
  }, [user]);

  function toggle(code: string) {
    setSelected((s) => (s.includes(code) ? s.filter((c) => c !== code) : [...s, code]));
  }

  // datetime-local yields "YYYY-MM-DDTHH:mm"; append seconds for the API.
  const withSeconds = (v: string) => (v.length === 16 ? `${v}:00` : v);

  async function onGenerate(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (selected.length === 0) return setError("Select at least one shortcode.");
    if (!from || !to) return setError("Choose a start and end date/time.");
    if (from > to) return setError("Start must be before end.");
    const dests = destinations
      .split(/[\s,;]+/)
      .map((d) => d.trim())
      .filter(Boolean);
    setSubmitting(true);
    try {
      const job = await createJob(selected, withSeconds(from), withSeconds(to), dests);
      router.push(`/jobs/${job.job_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create job");
      setSubmitting(false);
    }
  }

  if (loading || !user) {
    return (
      <main>
        <p className="muted">Loading…</p>
      </main>
    );
  }

  return (
    <>
      <Nav user={user} />
      <main>
        <h1>New extraction</h1>
        <form onSubmit={onGenerate}>
          <div className="card">
            <h2>Shortcodes {selected.length > 0 && <span className="muted">· {selected.length} selected</span>}</h2>
            {shortcodes.length === 0 ? (
              <p className="muted">You have no authorized shortcodes. Ask an admin to grant access.</p>
            ) : (
              shortcodes.map((s) => (
                <label
                  key={s.id}
                  className={`checkitem${selected.includes(s.code) ? " selected" : ""}`}
                >
                  <input
                    type="checkbox"
                    checked={selected.includes(s.code)}
                    onChange={() => toggle(s.code)}
                  />
                  <span>
                    <strong>{s.code}</strong> — {s.name}
                  </span>
                </label>
              ))
            )}
          </div>

          <div className="card">
            <h2>Date/time range</h2>
            <label className="field">
              <span>Start</span>
              <input type="datetime-local" value={from} onChange={(e) => setFrom(e.target.value)} />
            </label>
            <label className="field">
              <span>End</span>
              <input type="datetime-local" value={to} onChange={(e) => setTo(e.target.value)} />
            </label>
          </div>

          <div className="card">
            <h2>
              Destination numbers <span className="muted">· optional</span>
            </h2>
            <p className="muted" style={{ marginTop: 0 }}>
              Limit results to specific <code>destination_addr</code> values. Leave empty to
              include all. Separate multiple numbers with commas, spaces, or new lines.
            </p>
            <label className="field">
              <span>destination_addr filter</span>
              <input
                value={destinations}
                onChange={(e) => setDestinations(e.target.value)}
                placeholder="923008618543, 923445424686"
              />
            </label>
          </div>

          {error && <p className="err">{error}</p>}
          <button className="btn" type="submit" disabled={submitting}>
            {submitting ? "Generating…" : "Generate report"}
          </button>
        </form>
      </main>
    </>
  );
}
