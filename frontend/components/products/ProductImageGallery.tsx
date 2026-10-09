"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronLeft, ChevronRight, Sprout, X } from "lucide-react";
import { mediaUrl } from "@/lib/format";

export function ProductImageGallery({
  images,
  title,
}: {
  images: string[];
  title: string;
}) {
  const productImages = Array.isArray(images) ? images.slice(0, 8) : [];
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [viewerIndex, setViewerIndex] = useState<number | null>(null);
  const touchStartX = useRef<number | null>(null);
  const selectedImage = productImages[selectedIndex];

  useEffect(() => {
    setSelectedIndex((current) =>
      productImages.length ? Math.min(current, productImages.length - 1) : 0
    );
    if (!productImages.length) setViewerIndex(null);
  }, [productImages.length]);

  useEffect(() => {
    if (viewerIndex === null) return;
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setViewerIndex(null);
      if (event.key === "ArrowRight") {
        setViewerIndex((current) =>
          current === null ? null : (current + 1) % productImages.length
        );
      }
      if (event.key === "ArrowLeft") {
        setViewerIndex((current) =>
          current === null
            ? null
            : (current - 1 + productImages.length) % productImages.length
        );
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [viewerIndex, productImages.length]);

  function moveViewer(direction: -1 | 1) {
    setViewerIndex((current) =>
      current === null
        ? null
        : (current + direction + productImages.length) % productImages.length
    );
  }

  return (
    <>
      <div className="mb-5">
        <button
          type="button"
          onClick={() => selectedImage && setViewerIndex(selectedIndex)}
          disabled={!selectedImage}
          aria-label={selectedImage ? `View ${title} image full size` : "No product image"}
          className="group relative flex h-64 w-full items-center justify-center overflow-hidden rounded-xl bg-gray-100 sm:h-80 lg:h-96"
        >
          {selectedImage ? (
            <>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={mediaUrl(selectedImage)}
                alt={title}
                className="h-full w-full object-contain"
              />
              <span className="absolute bottom-3 right-3 rounded-lg bg-gray-900/70 px-2.5 py-1.5 text-xs font-medium text-white opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100">
                Click to view full size
              </span>
            </>
          ) : (
            <Sprout className="h-10 w-10 text-gray-300" />
          )}
        </button>

        {productImages.length > 1 && (
          <div className="mt-3 flex gap-2 overflow-x-auto pb-1">
            {productImages.map((image, index) => (
              <button
                key={`${image}-${index}`}
                type="button"
                onClick={() => setSelectedIndex(index)}
                aria-label={`Show image ${index + 1} of ${productImages.length}`}
                aria-pressed={selectedIndex === index}
                className={`h-16 w-16 shrink-0 overflow-hidden rounded-lg border-2 bg-gray-50 sm:h-20 sm:w-20 ${
                  selectedIndex === index
                    ? "border-green-600"
                    : "border-transparent hover:border-gray-300"
                }`}
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={mediaUrl(image)}
                  alt={`${title} thumbnail ${index + 1}`}
                  className="h-full w-full object-cover"
                />
              </button>
            ))}
          </div>
        )}
      </div>

      {viewerIndex !== null && productImages.length > 0 && (
        <div
          className="fixed inset-0 z-[100] flex items-center justify-center bg-black/90 p-3 sm:p-8"
          role="dialog"
          aria-modal="true"
          aria-label={`${title} image viewer`}
          onClick={() => setViewerIndex(null)}
          onTouchStart={(event) => {
            touchStartX.current = event.changedTouches[0]?.clientX ?? null;
          }}
          onTouchEnd={(event) => {
            if (touchStartX.current === null) return;
            const difference =
              (event.changedTouches[0]?.clientX ?? touchStartX.current) -
              touchStartX.current;
            if (Math.abs(difference) > 50) moveViewer(difference < 0 ? 1 : -1);
            touchStartX.current = null;
          }}
        >
          <button
            type="button"
            onClick={() => setViewerIndex(null)}
            aria-label="Close image viewer"
            className="absolute right-3 top-3 z-10 rounded-full bg-white/10 p-2 text-white hover:bg-white/20 sm:right-6 sm:top-6"
          >
            <X className="h-6 w-6" />
          </button>
          {productImages.length > 1 && (
            <button
              type="button"
              onClick={(event) => {
                event.stopPropagation();
                moveViewer(-1);
              }}
              aria-label="Previous image"
              className="absolute left-2 z-10 rounded-full bg-white/10 p-2 text-white hover:bg-white/20 sm:left-6"
            >
              <ChevronLeft className="h-7 w-7" />
            </button>
          )}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={mediaUrl(productImages[viewerIndex])}
            alt={`${title}, image ${viewerIndex + 1}`}
            onClick={(event) => event.stopPropagation()}
            className="max-h-[86vh] max-w-[90vw] select-none object-contain"
          />
          {productImages.length > 1 && (
            <button
              type="button"
              onClick={(event) => {
                event.stopPropagation();
                moveViewer(1);
              }}
              aria-label="Next image"
              className="absolute right-2 z-10 rounded-full bg-white/10 p-2 text-white hover:bg-white/20 sm:right-6"
            >
              <ChevronRight className="h-7 w-7" />
            </button>
          )}
          <span className="absolute bottom-3 left-1/2 -translate-x-1/2 rounded-full bg-black/60 px-3 py-1 text-sm text-white">
            {viewerIndex + 1} / {productImages.length}
          </span>
        </div>
      )}
    </>
  );
}
