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
  alignment_zoom_png_url?: string;
  spectrogram_inhouse_png_url?: string;
  spectrogram_external_png_url?: string;
  spectrogram_aligned_png_url?: string;
  residual_rms_png_url?: string;
  anchor_candidates_png_url?: string;
}

// Tooltip component
const Tooltip = ({ text, children }: { text: string; children: React.ReactNode }) => (
  <div className="group relative inline-block">
    {children}
    <div className="invisible group-hover:visible absolute z-50 w-72 p-3 mt-1 text-xs leading-relaxed text-slate-200 bg-slate-800 border border-slate-600 shadow-xl opacity-0 group-hover:opacity-100 transition-opacity duration-200 pointer-events-none left-0" style={{ borderRadius: '2px' }}>
      {text}
    </div>
  </div>
);

export default function HomePage() {
  // File inputs
  const [inhouseFile, setInhouseFile] = useState<File | null>(null);
  const [externalFile, setExternalFile] = useState<File | null>(null);

  // Basic parameters
  const [mode, setMode] = useState("external_to_inhouse");
  const [anchorMode, setAnchorMode] = useState("xcorr");
  const [applyAlignment, setApplyAlignment] = useState(true);

  // Advanced parameters with predetermined values
  const [sampleRate, setSampleRate] = useState(48000);
  const [preferTrim, setPreferTrim] = useState(false);
  const [thresholdDb, setThresholdDb] = useState<number | null>(null);
  const [maxSearch, setMaxSearch] = useState(60.0);
  const [refStartSec, setRefStartSec] = useState(0.0);
  const [searchStartSec, setSearchStartSec] = useState(0.0);
  const [analysisSec, setAnalysisSec] = useState(30.0);
  const [templateSec, setTemplateSec] = useState(4.0);
  const [hopSec, setHopSec] = useState(0.1);
  const [minSim, setMinSim] = useState(0.78);
  const [generateWaveform, setGenerateWaveform] = useState(true);
  const [generateSimilarity, setGenerateSimilarity] = useState(true);

  // UI state
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [activeTab, setActiveTab] = useState<string>("waveform");
  const [status, setStatus] = useState<string | null>(null);
  const [result, setResult] = useState<ResultResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState(0);

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
    formData.append("apply", applyAlignment.toString());
    formData.append("sr", sampleRate.toString());
    formData.append("prefer_trim", preferTrim.toString());
    if (thresholdDb !== null) formData.append("threshold_db", thresholdDb.toString());
    formData.append("max_search", maxSearch.toString());
    formData.append("ref_start_sec", refStartSec.toString());
    formData.append("search_start_sec", searchStartSec.toString());
    formData.append("analysis_sec", analysisSec.toString());
    formData.append("template_sec", templateSec.toString());
    formData.append("hop_sec", hopSec.toString());
    formData.append("min_sim", minSim.toString());
    formData.append("generate_waveform_png", generateWaveform.toString());
    formData.append("generate_similarity_png", generateSimilarity.toString());

    try {
      const { data } = await axios.post<JobResponse>(
        `${apiBase}/api/v1/alignments`,
        formData,
        {
          headers: { "Content-Type": "multipart/form-data" },
        }
      );

      setStatus(`Job queued: ${data.job_id}`);

      if (progressTimerRef.current) {
        clearInterval(progressTimerRef.current);
      }
      progressTimerRef.current = setInterval(() => {
        setProgress((prev) => {
          if (prev >= 95) return prev;
          return prev + 3;
        });
      }, 1000);

      const poll = async () => {
        const res = await axios.get<ResultResponse>(
          `${apiBase}/api/v1/alignments/${data.job_id}`
        );

        setResult(res.data);
        setStatus(`Job status: ${res.data.status}`);

        if (res.data.status === "completed" || res.data.status === "failed") {
          setLoading(false);
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

  // Tab data
  const tabs = [
    { id: "waveform", label: "Waveform", hasContent: !!result?.waveform_png_url },
    { id: "similarity", label: "Similarity", hasContent: !!result?.similarity_png_url },
    { id: "alignment_zoom", label: "Alignment Zoom", hasContent: !!result?.alignment_zoom_png_url },
    { id: "spectrograms", label: "Spectrograms", hasContent: !!(result?.spectrogram_inhouse_png_url || result?.spectrogram_external_png_url || result?.spectrogram_aligned_png_url) },
    { id: "residual", label: "Residual Analysis", hasContent: !!result?.residual_rms_png_url },
    { id: "anchors", label: "Anchor Candidates", hasContent: !!result?.anchor_candidates_png_url },
  ];

  return (
    <main className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950 text-slate-50 py-12 px-4">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <header className="text-center mb-12">
          <h1 className="text-5xl font-bold mb-3 bg-gradient-to-r from-indigo-400 via-purple-400 to-pink-400 bg-clip-text text-transparent">
            Align Audio Studio
          </h1>
          <p className="text-slate-400 text-lg">
            Advanced audio alignment with cross-correlation and content-based anchoring
          </p>
        </header>

        {/* Main Form */}
        <section className="bg-slate-900/40 backdrop-blur-sm border border-slate-700/50 shadow-2xl p-8 mb-8" style={{ borderRadius: '2px' }}>
          <form onSubmit={handleSubmit} className="space-y-6">
            {/* File Uploads */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="space-y-2">
                <Tooltip text="Your reference audio file - this is the ground truth timeline that the external file will be aligned to.">
                  <label className="block text-sm font-semibold text-slate-300 uppercase tracking-wide cursor-help">
                    In-House Audio ⓘ
                  </label>
                </Tooltip>
                <div className="relative">
                  <input
                    type="file"
                    accept="audio/*"
                    onChange={(e: ChangeEvent<HTMLInputElement>) =>
                      setInhouseFile(e.target.files?.[0] ?? null)
                    }
                    className="block w-full text-sm text-slate-300 file:mr-4 file:py-3 file:px-5 file:border-0 file:text-sm file:font-semibold file:bg-gradient-to-r file:from-indigo-600 file:to-purple-600 file:text-white hover:file:from-indigo-500 hover:file:to-purple-500 file:transition-all file:duration-200 bg-slate-800/50 border border-slate-700 p-2"
                    style={{ borderRadius: '2px' }}
                  />
                </div>
                {inhouseFile && (
                  <p className="text-xs text-emerald-400 mt-1">✓ {inhouseFile.name}</p>
                )}
              </div>

              <div className="space-y-2">
                <Tooltip text="The audio file you want to align - this file's timing will be adjusted to match the in-house reference.">
                  <label className="block text-sm font-semibold text-slate-300 uppercase tracking-wide cursor-help">
                    External Audio ⓘ
                  </label>
                </Tooltip>
                <div className="relative">
                  <input
                    type="file"
                    accept="audio/*"
                    onChange={(e: ChangeEvent<HTMLInputElement>) =>
                      setExternalFile(e.target.files?.[0] ?? null)
                    }
                    className="block w-full text-sm text-slate-300 file:mr-4 file:py-3 file:px-5 file:border-0 file:text-sm file:font-semibold file:bg-gradient-to-r file:from-indigo-600 file:to-purple-600 file:text-white hover:file:from-indigo-500 hover:file:to-purple-500 file:transition-all file:duration-200 bg-slate-800/50 border border-slate-700 p-2"
                    style={{ borderRadius: '2px' }}
                  />
                </div>
                {externalFile && (
                  <p className="text-xs text-emerald-400 mt-1">✓ {externalFile.name}</p>
                )}
              </div>
            </div>

            {/* Basic Parameters */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div>
                <Tooltip text="xcorr uses FFT-based normalized cross-correlation (fast, works well for similar content). Content uses MFCC feature matching (better for finding specific audio segments in longer files).">
                  <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wide mb-2 cursor-help">
                    Anchor Mode ⓘ
                  </label>
                </Tooltip>
                <select
                  value={anchorMode}
                  onChange={(e) => setAnchorMode(e.target.value)}
                  className="w-full bg-slate-800 border border-slate-700 text-slate-100 px-4 py-3 text-sm font-medium focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition-all"
                  style={{ borderRadius: '2px' }}
                >
                  <option value="xcorr">Cross-Correlation (Fast)</option>
                  <option value="content">Content-Based (MFCC)</option>
                </select>
              </div>

              <div>
                <Tooltip text="Determines which file gets shifted. External→In-house means the external file will be padded/trimmed to align with in-house timing. In-house→External does the opposite.">
                  <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wide mb-2 cursor-help">
                    Shift Target ⓘ
                  </label>
                </Tooltip>
                <select
                  value={mode}
                  onChange={(e) => setMode(e.target.value)}
                  className="w-full bg-slate-800 border border-slate-700 text-slate-100 px-4 py-3 text-sm font-medium focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition-all"
                  style={{ borderRadius: '2px' }}
                >
                  <option value="external_to_inhouse">External → In-house</option>
                  <option value="inhouse_to_external">In-house → External</option>
                </select>
              </div>

              <div>
                <Tooltip text="Sample rate for analysis and output. Higher rates preserve more frequency information but increase processing time. 48kHz is standard for video production.">
                  <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wide mb-2 cursor-help">
                    Sample Rate (Hz) ⓘ
                  </label>
                </Tooltip>
                <select
                  value={sampleRate}
                  onChange={(e) => setSampleRate(Number(e.target.value))}
                  className="w-full bg-slate-800 border border-slate-700 text-slate-100 px-4 py-3 text-sm font-medium focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition-all"
                  style={{ borderRadius: '2px' }}
                >
                  <option value="44100">44100 Hz</option>
                  <option value="48000">48000 Hz</option>
                  <option value="96000">96000 Hz</option>
                </select>
              </div>
            </div>

            {/* Toggles */}
            <div className="flex flex-wrap gap-6 pt-2">
              <Tooltip text="When enabled, runs FFmpeg to generate the aligned audio file. Disable this if you only want to calculate the offset without creating output.">
                <label className="flex items-center gap-3 cursor-pointer group">
                  <input
                    type="checkbox"
                    checked={applyAlignment}
                    onChange={(e) => setApplyAlignment(e.target.checked)}
                    className="w-5 h-5 bg-slate-800 border-2 border-slate-600 text-indigo-600 focus:ring-2 focus:ring-indigo-500 focus:ring-offset-0 transition-all"
                    style={{ borderRadius: '2px' }}
                  />
                  <span className="text-sm font-medium text-slate-300 group-hover:text-slate-100 transition-colors">
                    Apply Alignment (Generate Output) ⓘ
                  </span>
                </label>
              </Tooltip>

              <Tooltip text="When enabled, the system will prefer trimming samples over adding silence for negative offsets (may result in data loss but avoids added latency).">
                <label className="flex items-center gap-3 cursor-pointer group">
                  <input
                    type="checkbox"
                    checked={preferTrim}
                    onChange={(e) => setPreferTrim(e.target.checked)}
                    className="w-5 h-5 bg-slate-800 border-2 border-slate-600 text-indigo-600 focus:ring-2 focus:ring-indigo-500 focus:ring-offset-0 transition-all"
                    style={{ borderRadius: '2px' }}
                  />
                  <span className="text-sm font-medium text-slate-300 group-hover:text-slate-100 transition-colors">
                    Prefer Trim over Pad ⓘ
                  </span>
                </label>
              </Tooltip>

              <Tooltip text="Generate a visualization showing the overlaid waveforms of both audio files for visual comparison.">
                <label className="flex items-center gap-3 cursor-pointer group">
                  <input
                    type="checkbox"
                    checked={generateWaveform}
                    onChange={(e) => setGenerateWaveform(e.target.checked)}
                    className="w-5 h-5 bg-slate-800 border-2 border-slate-600 text-indigo-600 focus:ring-2 focus:ring-indigo-500 focus:ring-offset-0 transition-all"
                    style={{ borderRadius: '2px' }}
                  />
                  <span className="text-sm font-medium text-slate-300 group-hover:text-slate-100 transition-colors">
                    Generate Waveform ⓘ
                  </span>
                </label>
              </Tooltip>

              <Tooltip text="Generate a plot showing the cross-correlation similarity score across different time offsets, helping visualize alignment confidence.">
                <label className="flex items-center gap-3 cursor-pointer group">
                  <input
                    type="checkbox"
                    checked={generateSimilarity}
                    onChange={(e) => setGenerateSimilarity(e.target.checked)}
                    className="w-5 h-5 bg-slate-800 border-2 border-slate-600 text-indigo-600 focus:ring-2 focus:ring-indigo-500 focus:ring-offset-0 transition-all"
                    style={{ borderRadius: '2px' }}
                  />
                  <span className="text-sm font-medium text-slate-300 group-hover:text-slate-100 transition-colors">
                    Generate Similarity Plot ⓘ
                  </span>
                </label>
              </Tooltip>
            </div>

            {/* Advanced Parameters Toggle */}
            <div className="border-t border-slate-700/50 pt-6">
              <button
                type="button"
                onClick={() => setShowAdvanced(!showAdvanced)}
                className="flex items-center gap-2 text-sm font-semibold text-slate-300 hover:text-indigo-400 transition-colors uppercase tracking-wide"
              >
                <span className={`transform transition-transform ${showAdvanced ? 'rotate-90' : ''}`}>▶</span>
                Advanced Parameters
              </button>
            </div>

            {/* Advanced Parameters */}
            {showAdvanced && (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6 pt-4">
                <div>
                  <Tooltip text="Maximum time range (±seconds) to search for alignment around zero lag. Larger values find offsets over longer distances but take more time.">
                    <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wide mb-2 cursor-help">
                      Max Search (seconds) ⓘ
                    </label>
                  </Tooltip>
                  <input
                    type="number"
                    step="0.1"
                    value={maxSearch}
                    onChange={(e) => setMaxSearch(Number(e.target.value))}
                    className="w-full bg-slate-800 border border-slate-700 text-slate-100 px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                    style={{ borderRadius: '2px' }}
                  />
                </div>

                <div>
                  <Tooltip text="Duration of in-house audio to use for analysis. Shorter windows speed up processing; longer windows may improve accuracy for complex audio.">
                    <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wide mb-2 cursor-help">
                      Analysis Window (sec) ⓘ
                    </label>
                  </Tooltip>
                  <input
                    type="number"
                    step="0.1"
                    value={analysisSec}
                    onChange={(e) => setAnalysisSec(Number(e.target.value))}
                    className="w-full bg-slate-800 border border-slate-700 text-slate-100 px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                    style={{ borderRadius: '2px' }}
                  />
                </div>

                <div>
                  <Tooltip text="Optional noise gate threshold in dB. Audio below this level is ignored during analysis. Useful for removing background noise. Leave empty to disable gating.">
                    <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wide mb-2 cursor-help">
                      Threshold dB (optional) ⓘ
                    </label>
                  </Tooltip>
                  <input
                    type="number"
                    step="0.1"
                    value={thresholdDb ?? ''}
                    onChange={(e) => setThresholdDb(e.target.value ? Number(e.target.value) : null)}
                    placeholder="None"
                    className="w-full bg-slate-800 border border-slate-700 text-slate-100 px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                    style={{ borderRadius: '2px' }}
                  />
                </div>

                <div>
                  <Tooltip text="Starting point (in seconds) within the in-house reference audio for analysis. Use non-zero values to skip intro segments.">
                    <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wide mb-2 cursor-help">
                      Ref Start (seconds) ⓘ
                    </label>
                  </Tooltip>
                  <input
                    type="number"
                    step="0.1"
                    value={refStartSec}
                    onChange={(e) => setRefStartSec(Number(e.target.value))}
                    className="w-full bg-slate-800 border border-slate-700 text-slate-100 px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                    style={{ borderRadius: '2px' }}
                  />
                </div>

                <div>
                  <Tooltip text="Starting point (in seconds) within the external search audio. Use this to skip known intro segments that don't need alignment.">
                    <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wide mb-2 cursor-help">
                      Search Start (seconds) ⓘ
                    </label>
                  </Tooltip>
                  <input
                    type="number"
                    step="0.1"
                    value={searchStartSec}
                    onChange={(e) => setSearchStartSec(Number(e.target.value))}
                    className="w-full bg-slate-800 border border-slate-700 text-slate-100 px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                    style={{ borderRadius: '2px' }}
                  />
                </div>

                <div>
                  <Tooltip text="(Content mode only) Duration of the template extracted from in-house audio for MFCC feature matching. Shorter templates are more flexible; longer ones are more specific.">
                    <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wide mb-2 cursor-help">
                      Template Size (sec) ⓘ
                    </label>
                  </Tooltip>
                  <input
                    type="number"
                    step="0.1"
                    value={templateSec}
                    onChange={(e) => setTemplateSec(Number(e.target.value))}
                    className="w-full bg-slate-800 border border-slate-700 text-slate-100 px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                    style={{ borderRadius: '2px' }}
                  />
                </div>

                <div>
                  <Tooltip text="(Content mode only) Time step between consecutive MFCC analysis windows. Smaller values are more precise but slower; larger values are faster but may miss the optimal match.">
                    <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wide mb-2 cursor-help">
                      Hop Size (seconds) ⓘ
                    </label>
                  </Tooltip>
                  <input
                    type="number"
                    step="0.01"
                    value={hopSec}
                    onChange={(e) => setHopSec(Number(e.target.value))}
                    className="w-full bg-slate-800 border border-slate-700 text-slate-100 px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                    style={{ borderRadius: '2px' }}
                  />
                </div>

                <div>
                  <Tooltip text="(Content mode only) Minimum cosine similarity (0-1) required to accept a match. Higher values (e.g., 0.9) are stricter; lower values (e.g., 0.7) are more permissive.">
                    <label className="block text-xs font-semibold text-slate-400 uppercase tracking-wide mb-2 cursor-help">
                      Min Similarity ⓘ
                    </label>
                  </Tooltip>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    max="1"
                    value={minSim}
                    onChange={(e) => setMinSim(Number(e.target.value))}
                    className="w-full bg-slate-800 border border-slate-700 text-slate-100 px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                    style={{ borderRadius: '2px' }}
                  />
                </div>
              </div>
            )}

            {/* Submit Button */}
            <div className="pt-4">
              <button
                type="submit"
                disabled={loading || !inhouseFile || !externalFile}
                className="w-full sm:w-auto px-8 py-4 text-base font-bold text-white bg-gradient-to-r from-indigo-600 via-purple-600 to-pink-600 hover:from-indigo-500 hover:via-purple-500 hover:to-pink-500 disabled:from-slate-700 disabled:via-slate-700 disabled:to-slate-700 disabled:cursor-not-allowed shadow-lg hover:shadow-xl transition-all duration-200 uppercase tracking-wide"
                style={{ borderRadius: '2px' }}
              >
                {loading ? "Processing..." : "Align Audio"}
              </button>
            </div>
          </form>

          {/* Status */}
          {status && (
            <div className="mt-6 p-4 bg-slate-800/50 border border-slate-700" style={{ borderRadius: '2px' }}>
              <p className="text-sm text-slate-300 font-mono">{status}</p>
            </div>
          )}
        </section>

        {/* Results Section */}
        {result && (
          <section className="bg-slate-900/40 backdrop-blur-sm border border-slate-700/50 shadow-2xl p-8" style={{ borderRadius: '2px' }}>
            <h2 className="text-2xl font-bold mb-6 text-indigo-400 uppercase tracking-wide">Results</h2>

            {result.status !== "completed" && (
              <div className="space-y-3">
                <p className="text-sm text-slate-300">
                  Status: <span className="font-mono font-semibold text-indigo-400">{result.status}</span>
                </p>
                <div className="w-full h-3 bg-slate-800 overflow-hidden" style={{ borderRadius: '2px' }}>
                  <div
                    className="h-full bg-gradient-to-r from-indigo-600 to-purple-600 transition-all duration-500"
                    style={{ width: `${progress}%` }}
                  />
                </div>
                <p className="text-xs text-slate-500">
                  Processing alignment — this may take a moment for larger files
                </p>
              </div>
            )}

            {result.status === "completed" && (
              <div className="space-y-6">
                {result.offset_sec !== undefined && (
                  <div className="p-4 bg-slate-800/50 border border-slate-700" style={{ borderRadius: '2px' }}>
                    <p className="text-sm text-slate-400 uppercase tracking-wide mb-1">Computed Offset</p>
                    <p className="text-3xl font-bold font-mono text-emerald-400">
                      {result.offset_sec.toFixed(6)} s
                    </p>
                  </div>
                )}

                {result.ffmpeg_command && (
                  <div>
                    <p className="text-sm font-semibold text-slate-300 uppercase tracking-wide mb-2">
                      FFmpeg Command
                    </p>
                    <pre className="bg-black/60 border border-slate-700 p-4 text-xs text-emerald-300 overflow-x-auto font-mono" style={{ borderRadius: '2px' }}>
                      {result.ffmpeg_command}
                    </pre>
                  </div>
                )}

                {/* Tabbed Visualizations */}
                <div>
                  <p className="text-sm font-semibold text-slate-300 uppercase tracking-wide mb-3">
                    Diagnostic Visualizations
                  </p>

                  {/* Tabs */}
                  <div className="flex flex-wrap gap-2 mb-4 border-b border-slate-700 pb-2">
                    {tabs.map((tab) => (
                      <button
                        key={tab.id}
                        onClick={() => setActiveTab(tab.id)}
                        disabled={!tab.hasContent}
                        className={`px-4 py-2 text-sm font-medium uppercase tracking-wide transition-all ${activeTab === tab.id
                          ? 'bg-indigo-600 text-white border-b-2 border-indigo-400'
                          : tab.hasContent
                            ? 'bg-slate-800 text-slate-300 hover:bg-slate-700'
                            : 'bg-slate-900 text-slate-600 cursor-not-allowed opacity-50'
                          }`}
                        style={{ borderRadius: '2px 2px 0 0' }}
                      >
                        {tab.label}
                      </button>
                    ))}
                  </div>

                  {/* Tab Content */}
                  <div className="bg-slate-800/30 border border-slate-700 p-4" style={{ borderRadius: '2px' }}>
                    {activeTab === "waveform" && result.waveform_png_url && (
                      <div>
                        <h3 className="text-sm font-bold text-slate-200 mb-2 uppercase tracking-wide">Waveform Overlay</h3>
                        <p className="text-xs text-slate-400 mb-3 leading-relaxed">
                          This visualization overlays the waveforms of your in-house reference audio (typically in blue) and the aligned external audio (typically in orange/red).
                          The waveforms show the amplitude of the audio signal over time. After successful alignment, you should see the two waveforms closely tracking each other,
                          with major peaks and valleys occurring at the same time positions. Misalignment would appear as visible time-shifted patterns. Use this to visually confirm
                          that the computed offset has properly synchronized the two audio streams. Note that the waveforms may not match perfectly in amplitude if the recordings
                          have different gain levels, but their temporal patterns should align.
                        </p>
                        <img
                          src={`${apiBase}${result.waveform_png_url}`}
                          alt="Waveform overlay"
                          className="w-full border border-slate-700 shadow-lg"
                          style={{ borderRadius: '2px' }}
                        />
                      </div>
                    )}

                    {activeTab === "similarity" && result.similarity_png_url && (
                      <div>
                        <h3 className="text-sm font-bold text-slate-200 mb-2 uppercase tracking-wide">Similarity Plot</h3>
                        <p className="text-xs text-slate-400 mb-3 leading-relaxed">
                          This graph shows the normalized cross-correlation similarity score as a function of time offset between the two audio files. The X-axis represents
                          different time offsets (in seconds), while the Y-axis shows the similarity score (0 to 1, where 1 is perfect correlation). The algorithm searches
                          for the offset that produces the highest similarity peak. A sharp, prominent peak indicates high confidence in the detected offset, while multiple
                          similar peaks or a flat curve suggests the audio files may not share enough common content for reliable alignment. The vertical line or marker
                          typically indicates the selected optimal offset. Look for a clear, distinctive peak well above the baseline for best alignment confidence.
                        </p>
                        <img
                          src={`${apiBase}${result.similarity_png_url}`}
                          alt="Similarity curve"
                          className="w-full border border-slate-700 shadow-lg"
                          style={{ borderRadius: '2px' }}
                        />
                      </div>
                    )}

                    {activeTab === "alignment_zoom" && result.alignment_zoom_png_url && (
                      <div>
                        <h3 className="text-sm font-bold text-slate-200 mb-2 uppercase tracking-wide">Alignment Zoom</h3>
                        <p className="text-xs text-slate-400 mb-3 leading-relaxed">
                          This zoomed-in view focuses on a specific time window around the alignment region, allowing you to inspect the quality of the alignment at a finer
                          granularity. Unlike the full waveform overlay which shows the entire audio duration, this zoom provides a detailed look at how well the waveforms
                          match in a critical section. You can observe sample-level accuracy and identify any subtle timing discrepancies that might not be visible in the
                          full view. This is particularly useful for verifying frame-accurate or sub-frame alignment quality. Perfect alignment will show waveforms that
                          overlap almost exactly, while even small misalignments will be visible as slight shifts between corresponding features.
                        </p>
                        <img
                          src={`${apiBase}${result.alignment_zoom_png_url}`}
                          alt="Alignment zoom"
                          className="w-full border border-slate-700 shadow-lg"
                          style={{ borderRadius: '2px' }}
                        />
                      </div>
                    )}

                    {activeTab === "spectrograms" && (
                      <div className="space-y-4">
                        <h3 className="text-sm font-bold text-slate-200 mb-2 uppercase tracking-wide">Spectrograms</h3>
                        <p className="text-xs text-slate-400 mb-3 leading-relaxed">
                          Spectrograms provide a time-frequency representation of your audio, showing how the frequency content evolves over time. The X-axis represents time,
                          the Y-axis represents frequency (Hz), and the color intensity indicates the magnitude or energy at each time-frequency point (brighter/warmer colors
                          typically mean higher energy). These visualizations are invaluable for identifying differences in audio quality, compression artifacts, or content
                          variations between recordings. Compare the in-house and external spectrograms to understand what frequency components are present in each. The aligned
                          spectrogram shows the external audio after time-shifting. Look for horizontal bands (constant frequencies), vertical lines (transient sounds like
                          percussion), and overall spectral similarity between the in-house and aligned versions to confirm successful alignment.
                        </p>
                        {result.spectrogram_inhouse_png_url && (
                          <div>
                            <p className="text-xs font-semibold text-slate-300 mb-2">In-House Spectrogram (Reference)</p>
                            <img
                              src={`${apiBase}${result.spectrogram_inhouse_png_url}`}
                              alt="In-house spectrogram"
                              className="w-full border border-slate-700 shadow-lg"
                              style={{ borderRadius: '2px' }}
                            />
                          </div>
                        )}
                        {result.spectrogram_external_png_url && (
                          <div>
                            <p className="text-xs font-semibold text-slate-300 mb-2">External Spectrogram (Original, Before Alignment)</p>
                            <img
                              src={`${apiBase}${result.spectrogram_external_png_url}`}
                              alt="External spectrogram"
                              className="w-full border border-slate-700 shadow-lg"
                              style={{ borderRadius: '2px' }}
                            />
                          </div>
                        )}
                        {result.spectrogram_aligned_png_url && (
                          <div>
                            <p className="text-xs font-semibold text-slate-300 mb-2">Aligned Spectrogram (External After Time-Shift)</p>
                            <img
                              src={`${apiBase}${result.spectrogram_aligned_png_url}`}
                              alt="Aligned spectrogram"
                              className="w-full border border-slate-700 shadow-lg"
                              style={{ borderRadius: '2px' }}
                            />
                          </div>
                        )}
                      </div>
                    )}

                    {activeTab === "residual" && result.residual_rms_png_url && (
                      <div>
                        <h3 className="text-sm font-bold text-slate-200 mb-2 uppercase tracking-wide">Residual Analysis</h3>
                        <p className="text-xs text-slate-400 mb-3 leading-relaxed">
                          The residual RMS (Root Mean Square) plot shows the difference between the in-house reference audio and the aligned external audio over time.
                          This is computed by subtracting the two aligned signals and measuring the energy of the difference (residual). Lower residual values indicate
                          better alignment and higher similarity between the audio sources. The X-axis shows time, and the Y-axis shows the RMS energy of the residual
                          signal. Ideally, you want to see consistently low values throughout, especially in regions where both audio files contain the same content.
                          High residual spikes may indicate areas where the content differs (e.g., different mastering, compression, or edits), or where alignment quality
                          degrades. This metric is useful for quantitatively assessing alignment quality and identifying problematic time regions that may need manual review.
                        </p>
                        <img
                          src={`${apiBase}${result.residual_rms_png_url}`}
                          alt="Residual RMS"
                          className="w-full border border-slate-700 shadow-lg"
                          style={{ borderRadius: '2px' }}
                        />
                      </div>
                    )}

                    {activeTab === "anchors" && result.anchor_candidates_png_url && (
                      <div>
                        <h3 className="text-sm font-bold text-slate-200 mb-2 uppercase tracking-wide">Anchor Candidates</h3>
                        <p className="text-xs text-slate-400 mb-3 leading-relaxed">
                          This visualization shows the candidate anchor points that were evaluated during the alignment process. When using content-based (MFCC) anchor mode,
                          the algorithm identifies potential matching positions between the reference template and the search audio. Each candidate represents a possible
                          alignment point with an associated similarity score. The graph typically displays these candidates along a timeline, with markers indicating their
                          positions and scores (often shown by color intensity or marker size). The selected anchor point(s) — those with the highest similarity scores —
                          are used to compute the final alignment offset. This diagnostic is useful for understanding why a particular offset was chosen and for troubleshooting
                          cases where the wrong anchor may have been selected due to repetitive content or low-quality audio. Multiple strong candidates suggest the audio
                          contains repetitive patterns, while a single dominant candidate indicates a unique, easily identifiable alignment point.
                        </p>
                        <img
                          src={`${apiBase}${result.anchor_candidates_png_url}`}
                          alt="Anchor candidates"
                          className="w-full border border-slate-700 shadow-lg"
                          style={{ borderRadius: '2px' }}
                        />
                      </div>
                    )}
                  </div>
                </div>

                {/* Audio Players */}
                <div className="space-y-4 pt-4">
                  {result.inhouse_url && (
                    <div className="p-4 bg-slate-800/30 border border-slate-700" style={{ borderRadius: '2px' }}>
                      <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-2">
                        In-House (Reference) Audio
                      </p>
                      <audio
                        controls
                        src={`${apiBase}${result.inhouse_url}`}
                        className="w-full"
                      />
                    </div>
                  )}

                  {result.external_url && (
                    <div className="p-4 bg-slate-800/30 border border-slate-700" style={{ borderRadius: '2px' }}>
                      <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-2">
                        External (Original) Audio
                      </p>
                      <audio
                        controls
                        src={`${apiBase}${result.external_url}`}
                        className="w-full"
                      />
                    </div>
                  )}

                  {result.aligned_audio_url && (
                    <div className="p-4 bg-emerald-900/20 border border-emerald-700/50" style={{ borderRadius: '2px' }}>
                      <p className="text-xs font-semibold text-emerald-400 uppercase tracking-wide mb-2">
                        Aligned Audio (Output)
                      </p>
                      <audio
                        controls
                        src={`${apiBase}${result.aligned_audio_url}`}
                        className="w-full"
                      />
                    </div>
                  )}
                </div>
              </div>
            )}
          </section>
        )}
      </div>
    </main>
  );
}
