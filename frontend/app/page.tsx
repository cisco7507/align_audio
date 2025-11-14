"use client";

import { ChangeEvent, FormEvent, useEffect, useRef, useState } from "react";
import axios from "axios";

interface JobResponse {
  job_id: string;
  status: string;
}

interface ResultResponse {
  job_id: string;
  status: string;
  offset_sec?: number;
  ffmpeg_command?: string;
  inhouse_url?: string;
  external_url?: string;
  aligned_audio_url?: string;
  waveform_png_url?: string;
  similarity_png_url?: string;
}

export default function HomePage() {
  const [inhouseFile, setInhouseFile] = useState<File | null>(null);
  const [externalFile, setExternalFile] = useState<File | null>(null);
  const [mode, setMode] = useState("external_to_inhouse");
  const [anchorMode, setAnchorMode] = useState("xcorr");
  const [status, setStatus] = useState<string | null>(null);
  const [result, setResult] = useState<ResultResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [applyAlignment, setApplyAlignment] = useState(false);
  const [progress, setProgress] = useState(0);

  // Track a timer that advances pseudo-progress while the job is in-flight.
  const progressTimerRef = useRef<NodeJS.Timeout | null>(null);

  const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!inhouseFile || !externalFile) return;
    setLoading(true);
    setStatus("Uploading and creating job...");
    setResult(null);
    setProgress(0);

    const formData = new FormData();
    formData.append("inhouse_file", inhouseFile);
    formData.append("external_file", externalFile);
  formData.append("mode", mode);
  formData.append("anchor_mode", anchorMode);
  formData.append("apply", applyAlignment ? "true" : "false");

    try {
      const { data } = await axios.post<JobResponse>(
        `${apiBase}/api/v1/alignments`,
        formData,
        {
          headers: { "Content-Type": "multipart/form-data" },
        }
      );

      setStatus(`Job queued: ${data.job_id}`);

      // Start a pseudo-progress timer that slowly advances up to 95%
      if (progressTimerRef.current) {
        clearInterval(progressTimerRef.current);
      }
      progressTimerRef.current = setInterval(() => {
        setProgress((prev) => {
          // Don't let pseudo-progress reach 100% until the job actually completes.
          if (prev >= 95) return prev;
          return prev + 3;
        });
      }, 1000);

      // Poll for result
      const poll = async () => {
        const res = await axios.get<ResultResponse>(
          `${apiBase}/api/v1/alignments/${data.job_id}`
        );

        // Always capture the latest job payload so the Results card (and
        // progress bar for non-completed states) can render.
        setResult(res.data);
        setStatus(`Job status: ${res.data.status}`);

        if (res.data.status === "completed" || res.data.status === "failed") {
          setLoading(false);
          // Snap to 100% when the job is finished (or failed).
          setProgress(100);
          if (progressTimerRef.current) {
            clearInterval(progressTimerRef.current);
            progressTimerRef.current = null;
          }
        } else {
          setTimeout(poll, 1500);
        }
      };

      poll();
    } catch (err) {
      console.error(err);
      setStatus("Error creating job");
      setLoading(false);
    }
  };

  return (
    <main className="min-h-screen bg-slate-950 text-slate-50 flex flex-col items-center py-10 px-4">
      <div className="w-full max-w-3xl">
        <header className="mb-8">
          <h1 className="text-3xl font-semibold mb-2">Align Audio Studio</h1>
          <p className="text-slate-300">
            Upload in-house and external audio, then compute alignment using xcorr
            or content-based anchors.
          </p>
        </header>

        <section className="bg-slate-900/70 border border-slate-800 rounded-xl p-6 mb-6 shadow-lg">
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-1">In-house audio</label>
              <input
                type="file"
                accept="audio/*"
                onChange={(e: ChangeEvent<HTMLInputElement>) =>
                  setInhouseFile(e.target.files?.[0] ?? null)
                }
                className="block w-full text-sm text-slate-200 file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 file:text-sm file:font-semibold file:bg-indigo-500 file:text-white hover:file:bg-indigo-600"
              />
            </div>

            <div>
              <label className="block text-sm font-medium mb-1">External audio</label>
              <input
                type="file"
                accept="audio/*"
                onChange={(e: ChangeEvent<HTMLInputElement>) =>
                  setExternalFile(e.target.files?.[0] ?? null)
                }
                className="block w-full text-sm text-slate-200 file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 file:text-sm file:font-semibold file:bg-indigo-500 file:text-white hover:file:bg-indigo-600"
              />
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium mb-1">Anchor mode</label>
                <select
                  value={anchorMode}
                  onChange={(e) => setAnchorMode(e.target.value)}
                  className="w-full rounded-md bg-slate-950 border border-slate-700 px-3 py-2 text-sm"
                >
                  <option value="xcorr">xcorr (fast)</option>
                  <option value="content">content (MFCC)</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium mb-1">Shift target</label>
                <select
                  value={mode}
                  onChange={(e) => setMode(e.target.value)}
                  className="w-full rounded-md bg-slate-950 border border-slate-700 px-3 py-2 text-sm"
                >
                  <option value="external_to_inhouse">External → In-house</option>
                  <option value="inhouse_to_external">In-house → External</option>
                </select>
              </div>
            </div>

            <div className="flex items-center gap-2 pt-1">
              <input
                id="apply-alignment"
                type="checkbox"
                checked={applyAlignment}
                onChange={(e) => setApplyAlignment(e.target.checked)}
                className="h-4 w-4 rounded border-slate-600 bg-slate-950 text-indigo-500"
              />
              <label
                htmlFor="apply-alignment"
                className="text-xs text-slate-300"
              >
                Render aligned audio file (runs ffmpeg)
              </label>
            </div>

            <button
              type="submit"
              disabled={loading || !inhouseFile || !externalFile}
              className="mt-2 inline-flex items-center justify-center rounded-md bg-indigo-500 px-4 py-2 text-sm font-medium text-white shadow hover:bg-indigo-600 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {loading ? "Aligning..." : "Align audio"}
            </button>
          </form>

          {status && (
            <p className="mt-4 text-sm text-slate-300">{status}</p>
          )}
        </section>

        {result && (
          <section className="bg-slate-900/70 border border-slate-800 rounded-xl p-6 shadow-lg space-y-4">
            <h2 className="text-xl font-semibold mb-2">Results</h2>

            {result.status !== "completed" && (
              <div className="space-y-2">
                <p className="text-sm text-slate-300">
                  Job status: <span className="font-mono">{result.status}</span>
                </p>
                <div className="w-full h-2 rounded-full bg-slate-800 overflow-hidden">
                  <div
                    className="h-full bg-indigo-500 transition-[width] duration-500"
                    style={{ width: `${progress}%` }}
                  />
                </div>
                <p className="text-xs text-slate-500">
                  Computing alignment; this may take a moment for longer files.
                </p>
              </div>
            )}

            {result.status === "completed" && (
              <>
                {result.offset_sec !== undefined && (
                  <p className="text-sm">
                    Offset: <span className="font-mono">{result.offset_sec.toFixed(6)} s</span>
                  </p>
                )}

                {result.ffmpeg_command && (
                  <div>
                    <p className="text-sm font-medium mb-1">Suggested FFmpeg command:</p>
                    <pre className="bg-black/60 rounded-md p-3 text-xs overflow-x-auto">
                      {result.ffmpeg_command}
                    </pre>
                  </div>
                )}

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {result.waveform_png_url && (
                    <div>
                      <p className="text-sm font-medium mb-1">Waveform overlay</p>
                      <img
                        src={`${apiBase}${result.waveform_png_url}`}
                        alt="Waveform overlay"
                        className="w-full rounded-md border border-slate-800"
                      />
                    </div>
                  )}

                  {result.similarity_png_url && (
                    <div>
                      <p className="text-sm font-medium mb-1">Similarity curve</p>
                      <img
                        src={`${apiBase}${result.similarity_png_url}`}
                        alt="Similarity curve"
                        className="w-full rounded-md border border-slate-800"
                      />
                    </div>
                  )}
                </div>

                <div className="space-y-3 mt-2">
                  {result.inhouse_url && (
                    <div>
                      <p className="text-xs font-medium text-slate-300 mb-1">
                        In-house (reference) audio
                      </p>
                      <audio
                        controls
                        src={`${apiBase}${result.inhouse_url}`}
                        className="w-full"
                      />
                    </div>
                  )}

                  {result.external_url && (
                    <div>
                      <p className="text-xs font-medium text-slate-300 mb-1">
                        External (original) audio
                      </p>
                      <audio
                        controls
                        src={`${apiBase}${result.external_url}`}
                        className="w-full"
                      />
                    </div>
                  )}

                  {result.aligned_audio_url && (
                    <div>
                      <p className="text-xs font-medium text-emerald-300 mb-1">
                        Aligned audio (output)
                      </p>
                      <audio
                        controls
                        src={`${apiBase}${result.aligned_audio_url}`}
                        className="w-full"
                      />
                    </div>
                  )}
                </div>
              </>
            )}
          </section>
        )}
      </div>
    </main>
  );
}
