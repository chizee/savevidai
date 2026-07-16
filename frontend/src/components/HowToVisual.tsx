/**
 * Annotated "how to download" process graphic for the hero's empty space.
 * Inline SVG on purpose: it inherits the design-token CSS variables, so the
 * mock UI recolors itself in light/dark, and the red marker annotations stay
 * crisp at any DPI. Purely decorative-instructional; the crawlable text
 * version lives in the static landing section below.
 */

const RED = "#ff5148";

export function HowToVisual() {
  return (
    <figure className="mx-auto mt-14 w-full max-w-xl">
      <svg
        viewBox="0 0 560 1010"
        role="img"
        aria-label="How to download: copy the post link from Twitter, paste it in the box, then pick a quality to save the video"
        className="h-auto w-full"
      >
        {/* ── Step 1: tweet mock with Copy link menu ── */}
        <g>
          <rect x="24" y="22" width="512" height="272" rx="22" fill="var(--card)" stroke="var(--line)" />
          <circle cx="72" cy="70" r="17" fill="var(--pill)" />
          <rect x="102" y="56" width="110" height="11" rx="5.5" fill="var(--pill)" />
          <rect x="102" y="75" width="72" height="9" rx="4.5" fill="var(--pill)" />
          {/* thumbnail */}
          <rect x="48" y="106" width="330" height="160" rx="14" fill="var(--pill)" />
          <circle cx="213" cy="186" r="27" fill="var(--accent)" opacity="0.9" />
          <path d="M205 172 L228 186 L205 200 Z" fill="#fff" />
          {/* share menu card */}
          <rect x="396" y="120" width="136" height="92" rx="14" fill="var(--card)" stroke="var(--line)" />
          <path d="M414 148 a7 7 0 1 1 6 3 l-4 6 a7 7 0 1 1 -6 -3 Z" fill="none" stroke="var(--fg)" strokeWidth="2.4" />
          <text x="434" y="153" fontFamily="var(--font-sans)" fontSize="16.5" fontWeight="600" fill="var(--fg)">
            Copy link
          </text>
          <rect x="414" y="176" width="86" height="9" rx="4.5" fill="var(--pill)" />
          {/* red marker: wobbly circle around Copy link + badge 1 */}
          <path
            d="M405 128 C438 116 528 118 536 140 C544 164 508 172 462 171 C420 170 396 160 399 145 C401 135 414 128 432 126"
            fill="none"
            stroke={RED}
            strokeWidth="5"
            strokeLinecap="round"
            opacity="0.95"
          />
          <circle cx="52" cy="46" r="16" fill={RED} />
          <text x="52" y="52" textAnchor="middle" fontFamily="var(--font-sans)" fontSize="18" fontWeight="700" fill="#fff">
            1
          </text>
        </g>

        {/* red arrow: menu → paste pill */}
        <path
          d="M470 186 C462 232 400 250 320 268 C286 276 268 292 264 314"
          fill="none"
          stroke={RED}
          strokeWidth="5"
          strokeLinecap="round"
          opacity="0.95"
        />
        <path d="M252 296 L264 318 L279 300" fill="none" stroke={RED} strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" opacity="0.95" />

        {/* ── Step 2: paste pill + Fetch ── */}
        <g>
          <rect x="24" y="348" width="380" height="58" rx="29" fill="var(--card)" stroke="var(--line)" />
          <text x="52" y="384" fontFamily="var(--font-mono)" fontSize="17" fill="var(--muted)">
            x.com/i/status/2071…
          </text>
          <rect x="416" y="348" width="120" height="58" rx="29" fill="var(--accent)" />
          <text x="476" y="384" textAnchor="middle" fontFamily="var(--font-sans)" fontSize="18.5" fontWeight="600" fill="#fff">
            Fetch
          </text>
          {/* red marker circle around the whole row + badge 2 */}
          <path
            d="M30 342 C130 322 480 324 544 352 C566 378 520 416 420 418 C260 424 20 420 12 384 C8 362 40 346 96 338"
            fill="none"
            stroke={RED}
            strokeWidth="5"
            strokeLinecap="round"
            opacity="0.95"
          />
          <circle cx="52" cy="330" r="16" fill={RED} />
          <text x="52" y="336" textAnchor="middle" fontFamily="var(--font-sans)" fontSize="18" fontWeight="700" fill="#fff">
            2
          </text>
        </g>

        {/* red arrow: paste → qualities */}
        <path
          d="M296 428 C304 462 296 484 284 506"
          fill="none"
          stroke={RED}
          strokeWidth="5"
          strokeLinecap="round"
          opacity="0.95"
        />
        <path d="M272 490 L282 510 L298 496" fill="none" stroke={RED} strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" opacity="0.95" />

        {/* ── Step 3: quality pills + saved file ── */}
        <g>
          <rect x="24" y="532" width="512" height="452" rx="22" fill="var(--card)" stroke="var(--line)" />
          {/* best quality pill (primary) */}
          <rect x="56" y="568" width="268" height="60" rx="30" fill="var(--accent)" />
          <text x="86" y="606" fontFamily="var(--font-sans)" fontSize="20" fontWeight="700" fill="#fff">
            1920×1080
          </text>
          <rect x="204" y="580" width="38" height="24" rx="12" fill="#ffffff" opacity="0.24" />
          <text x="223" y="597" textAnchor="middle" fontFamily="var(--font-sans)" fontSize="13" fontWeight="800" fill="#fff">
            HD
          </text>
          <text x="256" y="605" fontFamily="var(--font-mono)" fontSize="15" fill="#fff" opacity="0.85">
            34 MB
          </text>
          {/* secondary pills */}
          <rect x="56" y="646" width="240" height="56" rx="28" fill="var(--pill)" stroke="var(--line)" />
          <text x="86" y="681" fontFamily="var(--font-sans)" fontSize="18" fontWeight="600" fill="var(--fg)">
            1280×720
          </text>
          <text x="196" y="681" fontFamily="var(--font-mono)" fontSize="14" fill="var(--muted)">
            18 MB
          </text>
          <rect x="56" y="720" width="222" height="56" rx="28" fill="var(--pill)" stroke="var(--line)" />
          <text x="86" y="755" fontFamily="var(--font-sans)" fontSize="18" fontWeight="600" fill="var(--fg)">
            640×360
          </text>
          <text x="188" y="755" fontFamily="var(--font-mono)" fontSize="14" fill="var(--muted)">
            6 MB
          </text>
          {/* saved row */}
          <line x1="56" y1="812" x2="504" y2="812" stroke="var(--line)" />
          <circle cx="78" cy="862" r="17" fill="#34c759" />
          <path d="M70 862 L76 869 L87 855" fill="none" stroke="#fff" strokeWidth="3.4" strokeLinecap="round" strokeLinejoin="round" />
          <text x="106" y="859" fontFamily="var(--font-mono)" fontSize="15.5" fill="var(--fg)">
            ada_2071_1080p.mp4
          </text>
          <text x="106" y="881" fontFamily="var(--font-sans)" fontSize="14.5" fill="var(--muted)">
            saved to your device
          </text>
          <text x="56" y="946" fontFamily="var(--font-sans)" fontSize="15" fill="var(--faint)">
            No watermark. Straight from Twitter's CDN.
          </text>
          {/* red marker circle around best pill + badge 3 */}
          <path
            d="M50 560 C140 542 330 546 342 580 C352 612 300 640 200 642 C120 644 36 634 34 602 C33 582 60 566 110 558"
            fill="none"
            stroke={RED}
            strokeWidth="5"
            strokeLinecap="round"
            opacity="0.95"
          />
          <circle cx="52" cy="540" r="16" fill={RED} />
          <text x="52" y="546" textAnchor="middle" fontFamily="var(--font-sans)" fontSize="18" fontWeight="700" fill="#fff">
            3
          </text>
        </g>
      </svg>
      <figcaption className="sr-only">
        Copy the post link, paste it above, pick a quality, and the video saves with a clean
        filename.
      </figcaption>
    </figure>
  );
}
