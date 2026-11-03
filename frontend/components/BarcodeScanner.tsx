"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { BrowserMultiFormatReader } from "@zxing/browser";
import { BarcodeFormat, DecodeHintType } from "@zxing/library";
import { Camera, CheckCircle2, ImageIcon, Loader2, ScanLine, X } from "lucide-react";
import { useTheme } from "@/components/AppShell";
import { fieldClass, primaryButton, secondaryButton } from "@/components/ui";

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

  const inputClass = `${fieldClass(darkMode)} flex-1`;
  const muted = darkMode ? "text-ink-400" : "text-ink-500";

  return (
    <div className="space-y-4">
      <p className={`text-sm leading-relaxed ${muted}`}>{hint}</p>

      <div className="relative overflow-hidden rounded-3xl bg-ink-950 shadow-card">
        <video
          ref={videoRef}
          className={`aspect-[4/3] w-full object-cover ${cameraActive ? "block" : "hidden"}`}
          muted
          playsInline
          autoPlay
        />
        {!cameraActive && (
          <div className="flex aspect-[4/3] flex-col items-center justify-center gap-3 text-ink-400">
            {scanSuccess ? (
              <>
                <CheckCircle2 size={44} className="text-brand-400" />
                <p className="text-sm font-semibold text-brand-300">読み取りました</p>
              </>
            ) : (
              <>
                <ScanLine size={44} className="opacity-50" />
                <p className="text-sm">下のボタンでカメラを起動します</p>
              </>
            )}
          </div>
        )}
        {cameraActive && (
          <>
            {/* 読み取る範囲を示す四隅の目印 */}
            <div className="pointer-events-none absolute inset-8 sm:inset-12">
              <span className="absolute left-0 top-0 h-8 w-8 rounded-tl-2xl border-l-4 border-t-4 border-brand-400" />
              <span className="absolute right-0 top-0 h-8 w-8 rounded-tr-2xl border-r-4 border-t-4 border-brand-400" />
              <span className="absolute bottom-0 left-0 h-8 w-8 rounded-bl-2xl border-b-4 border-l-4 border-brand-400" />
              <span className="absolute bottom-0 right-0 h-8 w-8 rounded-br-2xl border-b-4 border-r-4 border-brand-400" />
            </div>
            <p className="pointer-events-none absolute bottom-4 left-0 right-0 text-center text-sm font-medium text-white drop-shadow">
              コードを枠の中に合わせてください
            </p>
          </>
        )}
      </div>

      <div className="grid gap-2.5">
        {!cameraActive ? (
          <button
            type="button"
            onClick={startCamera}
            disabled={disabled || startingCamera || scanSuccess}
            className={`${primaryButton} min-h-14 text-base`}
          >
            {startingCamera ? (
              <Loader2 size={20} className="animate-spin" />
            ) : (
              <Camera size={20} />
            )}
            カメラで読み取る
          </button>
        ) : (
          <button
            type="button"
            onClick={stopCamera}
            disabled={disabled}
            className={`${secondaryButton(darkMode)} min-h-14 text-base`}
          >
            <X size={20} />
            カメラを止める
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
          className={secondaryButton(darkMode)}
        >
          {decodingFile ? (
            <Loader2 size={18} className="animate-spin" />
          ) : (
            <ImageIcon size={18} />
          )}
          写真から読み取る
        </button>
      </div>

      <div className="flex gap-2">
        <input
          value={manualCode}
          onChange={(e) => setManualCode(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") submitManual();
          }}
          disabled={disabled || scanSuccess}
          placeholder="コードを入力（型番・JAN）"
          enterKeyHint="search"
          className={inputClass}
        />
        <button
          type="button"
          onClick={submitManual}
          disabled={disabled || !manualCode.trim() || scanSuccess}
          className={`${primaryButton} shrink-0`}
        >
          検索
        </button>
      </div>

      {error && (
        <p role="alert" className="text-sm font-medium text-red-500">
          {error}
        </p>
      )}
    </div>
  );
}
