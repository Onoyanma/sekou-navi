"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { BrowserMultiFormatReader } from "@zxing/browser";
import { BarcodeFormat, DecodeHintType } from "@zxing/library";
import { Barcode, Camera, CheckCircle2, ImageIcon, Loader2, ScanLine, X } from "lucide-react";
import { surfaceClass, useTheme } from "@/components/AppShell";

type BarcodeScannerProps = {
  onScan: (value: string, format?: string) => void;
  disabled?: boolean;
  hint?: string;
};

const SCAN_FORMATS = [
  BarcodeFormat.QR_CODE,
  BarcodeFormat.EAN_13,
  BarcodeFormat.EAN_8,
  BarcodeFormat.CODE_128,
  BarcodeFormat.CODE_39,
  BarcodeFormat.UPC_A,
  BarcodeFormat.UPC_E,
  BarcodeFormat.ITF,
];

const SCANNER_HINTS = new Map<DecodeHintType, unknown>([
  [DecodeHintType.POSSIBLE_FORMATS, SCAN_FORMATS],
  [DecodeHintType.TRY_HARDER, false],
]);

const SCANNER_OPTIONS = {
  delayBetweenScanAttempts: 60,
  delayBetweenScanSuccess: 100,
  tryPlayVideoTimeout: 4000,
};

const VIDEO_CONSTRAINTS: MediaStreamConstraints = {
  audio: false,
  video: {
    facingMode: { ideal: "environment" },
    width: { ideal: 1280 },
    height: { ideal: 720 },
    frameRate: { ideal: 30, min: 15 },
  },
};

function createReader() {
  return new BrowserMultiFormatReader(SCANNER_HINTS, SCANNER_OPTIONS);
}

function pickRearCamera(devices: MediaDeviceInfo[]) {
  if (devices.length === 0) return undefined;

  const rear = devices.find((device) =>
    /back|rear|後|environment|trás|arrière/i.test(device.label)
  );

  return rear?.deviceId ?? devices[devices.length - 1]?.deviceId;
}

export function BarcodeScanner({
  onScan,
  disabled = false,
  hint = "QRコード・バーコードをカメラで読み取るか、写真・番号を入力してください",
}: BarcodeScannerProps) {
  const { darkMode } = useTheme();
  const videoRef = useRef<HTMLVideoElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const readerRef = useRef<BrowserMultiFormatReader | null>(null);
  const controlsRef = useRef<{ stop: () => void } | null>(null);
  const handledScanRef = useRef(false);
  const [cameraActive, setCameraActive] = useState(false);
  const [startingCamera, setStartingCamera] = useState(false);
  const [decodingFile, setDecodingFile] = useState(false);
  const [scanSuccess, setScanSuccess] = useState(false);
  const [error, setError] = useState("");
  const [manualCode, setManualCode] = useState("");

  const getReader = useCallback(() => {
    if (!readerRef.current) {
      readerRef.current = createReader();
    }
    return readerRef.current;
  }, []);

  const stopCamera = useCallback(() => {
    controlsRef.current?.stop();
    controlsRef.current = null;
    setCameraActive(false);
  }, []);

  const handleScanSuccess = useCallback(
    (value: string, format?: string) => {
      const trimmed = value.trim();
      if (!trimmed || disabled || handledScanRef.current) {
        return;
      }

      handledScanRef.current = true;
      stopCamera();
      setScanSuccess(true);
      setError("");
      onScan(trimmed, format);

      window.setTimeout(() => {
        setScanSuccess(false);
        handledScanRef.current = false;
      }, 1800);
    },
    [disabled, onScan, stopCamera]
  );

  useEffect(() => {
    return () => {
      stopCamera();
      readerRef.current = null;
    };
  }, [stopCamera]);

  async function startCamera() {
    if (disabled || !videoRef.current) return;

    setError("");
    setScanSuccess(false);
    setStartingCamera(true);
    handledScanRef.current = false;
    stopCamera();

    try {
      const reader = getReader();
      const devices = await BrowserMultiFormatReader.listVideoInputDevices();
      const deviceId = pickRearCamera(devices);

      const controls = deviceId
        ? await reader.decodeFromVideoDevice(
            deviceId,
            videoRef.current,
            (result) => {
              if (result) {
                handleScanSuccess(
                  result.getText(),
                  String(result.getBarcodeFormat())
                );
              }
            }
          )
        : await reader.decodeFromConstraints(
            VIDEO_CONSTRAINTS,
            videoRef.current,
            (result) => {
              if (result) {
                handleScanSuccess(
                  result.getText(),
                  String(result.getBarcodeFormat())
                );
              }
            }
          );

      controlsRef.current = controls;
      setCameraActive(true);
    } catch (cameraError) {
      console.error(cameraError);
      setError(
        "カメラを起動できませんでした。ブラウザのカメラ許可を確認してください。"
      );
      stopCamera();
    } finally {
      setStartingCamera(false);
    }
  }

  async function scanFromFile(file: File) {
    if (disabled) return;

    setError("");
    setScanSuccess(false);
    setDecodingFile(true);
    stopCamera();

    const reader = getReader();
    const url = URL.createObjectURL(file);

    try {
      const result = await reader.decodeFromImageUrl(url);
      handleScanSuccess(result.getText(), String(result.getBarcodeFormat()));
    } catch {
      setError("画像からコードを読み取れませんでした");
    } finally {
      URL.revokeObjectURL(url);
      setDecodingFile(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  }

  function submitManual() {
    if (!manualCode.trim()) {
      setError("コードを入力してください");
      return;
    }
    handleScanSuccess(manualCode);
    setManualCode("");
  }

  const buttonClass = darkMode
    ? "inline-flex items-center justify-center gap-2 rounded-xl border border-slate-700 px-4 py-2.5 text-sm font-semibold text-slate-200 hover:bg-slate-800 disabled:opacity-50"
    : "inline-flex items-center justify-center gap-2 rounded-xl border border-slate-200 px-4 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50";

  const inputClass = darkMode
    ? "flex-1 rounded-xl border border-slate-700 bg-slate-950 px-4 py-3 text-white outline-none focus:border-blue-500"
    : "flex-1 rounded-xl border border-slate-200 px-4 py-3 outline-none focus:border-blue-500";

  return (
    <div className={`${surfaceClass(darkMode)} space-y-4 p-4 md:p-5`}>
      <div className="flex items-start gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-violet-100 text-violet-700">
          <Barcode size={20} />
        </div>
        <div>
          <p
            className={
              darkMode
                ? "font-semibold text-white"
                : "font-semibold text-slate-900"
            }
          >
            QR / バーコード読み取り
          </p>
          <p
            className={
              darkMode ? "mt-1 text-sm text-slate-400" : "mt-1 text-sm text-slate-500"
            }
          >
            {hint}
          </p>
        </div>
      </div>

      <div
        className={
          darkMode
            ? "relative overflow-hidden rounded-2xl border border-slate-800 bg-black"
            : "relative overflow-hidden rounded-2xl border border-slate-200 bg-black"
        }
      >
        <video
          ref={videoRef}
          className={`aspect-video w-full object-cover ${cameraActive ? "block" : "hidden"}`}
          muted
          playsInline
          autoPlay
        />
        {!cameraActive && (
          <div className="flex aspect-video flex-col items-center justify-center gap-2 text-slate-400">
            {scanSuccess ? (
              <>
                <CheckCircle2 size={40} className="text-emerald-400" />
                <p className="text-sm text-emerald-400">読み取り成功</p>
              </>
            ) : (
              <>
                <ScanLine size={40} className="opacity-40" />
                <p className="text-sm">カメラプレビュー</p>
              </>
            )}
          </div>
        )}
        {cameraActive && (
          <>
            <div className="pointer-events-none absolute inset-8 rounded-xl border-2 border-dashed border-emerald-400/80" />
            <p className="pointer-events-none absolute bottom-3 left-0 right-0 text-center text-xs font-medium text-emerald-300">
              コードを枠内に合わせてください
            </p>
          </>
        )}
      </div>

      <div className="flex flex-wrap gap-2">
        {!cameraActive ? (
          <button
            type="button"
            onClick={startCamera}
            disabled={disabled || startingCamera || scanSuccess}
            className="inline-flex items-center gap-2 rounded-xl bg-violet-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-violet-700 disabled:opacity-50"
          >
            {startingCamera ? (
              <Loader2 size={16} className="animate-spin" />
            ) : (
              <Camera size={16} />
            )}
            カメラで読み取る
          </button>
        ) : (
          <button
            type="button"
            onClick={stopCamera}
            disabled={disabled}
            className={buttonClass}
          >
            <X size={16} />
            カメラを停止
          </button>
        )}

        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) scanFromFile(file);
          }}
        />
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          disabled={disabled || decodingFile || scanSuccess}
          className={buttonClass}
        >
          {decodingFile ? (
            <Loader2 size={16} className="animate-spin" />
          ) : (
            <ImageIcon size={16} />
          )}
          写真から読み取る
        </button>
      </div>

      <div className="flex flex-wrap gap-2">
        <input
          value={manualCode}
          onChange={(e) => setManualCode(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") submitManual();
          }}
          disabled={disabled || scanSuccess}
          placeholder="コードを手入力（型番・JANなど）"
          className={inputClass}
        />
        <button
          type="button"
          onClick={submitManual}
          disabled={disabled || !manualCode.trim() || scanSuccess}
          className="shrink-0 rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
        >
          検索
        </button>
      </div>

      {error && <p className="text-sm text-red-500">{error}</p>}
    </div>
  );
}
