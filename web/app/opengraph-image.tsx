import { ImageResponse } from 'next/og'

export const alt = 'Hakiki: is this section still good law?'
export const size = { width: 1200, height: 630 }
export const contentType = 'image/png'

export default async function Image() {
  return new ImageResponse(
    (
      <div
        style={{
          height: '100%',
          width: '100%',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between',
          padding: '72px 80px',
          backgroundColor: '#FAF7F2',
          border: '14px solid #8E2C48',
        }}
      >
        {/* Header: Seal + Wordmark */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '20px' }}>
          <div
            style={{
              width: '76px',
              height: '76px',
              borderRadius: '50%',
              border: '3.5px solid #8E2C48',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: '44px',
              color: '#8E2C48',
              fontFamily: 'serif',
            }}
          >
            §
          </div>
          <div
            style={{
              fontSize: '52px',
              fontWeight: 600,
              color: '#18212B',
              letterSpacing: '-0.02em',
              fontFamily: 'serif',
            }}
          >
            Hakiki
          </div>
        </div>

        {/* Center: Main Question & Tagline */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div
            style={{
              fontSize: '58px',
              fontWeight: 600,
              color: '#18212B',
              lineHeight: 1.15,
              fontFamily: 'serif',
            }}
          >
            Is this section still good law?
          </div>
          <div
            style={{
              fontSize: '26px',
              color: '#4B5563',
              maxWidth: '960px',
              lineHeight: 1.45,
            }}
          >
            Checking Kenyan statutes against the court rulings that limited, upheld, or
            struck them down, in the courts’ own words.
          </div>
        </div>

        {/* Footer Bar */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            borderTop: '2px solid #E5E0D8',
            paddingTop: '24px',
          }}
        >
          <span style={{ fontSize: '22px', color: '#8E2C48', fontWeight: 600 }}>
            Built for LexHack 2026
          </span>
          <span style={{ fontSize: '20px', color: '#6B7280' }}>
            Kenya Law Citator
          </span>
        </div>
      </div>
    ),
    { ...size }
  )
}
