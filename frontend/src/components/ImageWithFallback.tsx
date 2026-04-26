import { useEffect, useState } from "react";

interface ImageWithFallbackProps {
  src?: string | null;
  label?: string | null;
  className: string;
  imageClassName?: string;
  alt?: string;
}

function fallbackInitial(label: string | null | undefined): string {
  const trimmed = label?.trim();
  return trimmed ? trimmed.slice(0, 1).toUpperCase() : "R";
}

export function ImageWithFallback({
  src,
  label,
  className,
  imageClassName,
  alt = ""
}: ImageWithFallbackProps) {
  const [failed, setFailed] = useState(false);
  const imageUrl = src?.trim() ?? "";
  const showImage = imageUrl.length > 0 && !failed;

  useEffect(() => {
    setFailed(false);
  }, [imageUrl]);

  return (
    <div className={`${className}${showImage ? "" : ` ${className}--placeholder`}`}>
      {showImage ? (
        <img
          src={imageUrl}
          alt={alt}
          className={imageClassName}
          loading="lazy"
          onError={() => setFailed(true)}
        />
      ) : (
        <span aria-hidden="true">{fallbackInitial(label)}</span>
      )}
    </div>
  );
}
