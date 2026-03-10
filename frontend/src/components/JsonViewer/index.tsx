import { useMemo, useState } from 'react';
import { Button, Typography } from 'antd';

interface Props {
  data: unknown;
}

const viewerBoxStyle: React.CSSProperties = {
  padding: 12,
  background: '#f5f5f5',
  borderRadius: 4,
  overflow: 'auto',
  fontSize: 12,
  whiteSpace: 'pre-wrap',
  wordBreak: 'break-word',
  overflowWrap: 'anywhere',
};

function renderPrimitive(value: unknown) {
  if (value === null || value === undefined || value === '') return '-';
  if (typeof value === 'string') {
    return (
      <Typography.Text
        style={{
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-word',
          overflowWrap: 'anywhere',
        }}
      >
        {value}
      </Typography.Text>
    );
  }
  return (
    <Typography.Text
      style={{
        whiteSpace: 'pre-wrap',
        wordBreak: 'break-word',
        overflowWrap: 'anywhere',
      }}
    >
      {String(value)}
    </Typography.Text>
  );
}

export default function JsonViewer({ data }: Props) {
  const [raw, setRaw] = useState(false);

  const { parsedData, rawText, isJsonLike } = useMemo(() => {
    if (typeof data === 'string') {
      try {
        const parsed = JSON.parse(data);
        return {
          parsedData: parsed,
          rawText: JSON.stringify(parsed, null, 2),
          isJsonLike: true,
        };
      } catch {
        return {
          parsedData: data,
          rawText: data,
          isJsonLike: false,
        };
      }
    }

    return {
      parsedData: data,
      rawText: JSON.stringify(data ?? null, null, 2),
      isJsonLike: typeof data === 'object' && data !== null,
    };
  }, [data]);

  if (raw) {
    return (
      <div>
        <Button type="link" size="small" onClick={() => setRaw(false)}>
          格式化
        </Button>
        <pre style={{ ...viewerBoxStyle, margin: 0 }}>{rawText}</pre>
      </div>
    );
  }

  let formattedContent: React.ReactNode;
  if (Array.isArray(parsedData)) {
    formattedContent = (
      <pre
        style={{
          margin: 0,
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-word',
          overflowWrap: 'anywhere',
        }}
      >
        {JSON.stringify(parsedData, null, 2)}
      </pre>
    );
  } else if (parsedData && typeof parsedData === 'object') {
    formattedContent = (
      <dl style={{ margin: 0 }}>
        {Object.entries(parsedData).map(([k, v]) => (
          <div key={k} style={{ marginBottom: 8 }}>
            <Typography.Text strong>{k}:</Typography.Text>{' '}
            {typeof v === 'object' && v !== null ? (
              <pre
                style={{
                  margin: '4px 0 0',
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word',
                  overflowWrap: 'anywhere',
                }}
              >
                {JSON.stringify(v, null, 2)}
              </pre>
            ) : (
              renderPrimitive(v)
            )}
          </div>
        ))}
      </dl>
    );
  } else {
    formattedContent = (
      <pre
        style={{
          margin: 0,
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-word',
          overflowWrap: 'anywhere',
        }}
      >
        {rawText}
      </pre>
    );
  }

  return (
    <div>
      {isJsonLike && (
        <Button type="link" size="small" onClick={() => setRaw(true)}>
          原始 JSON
        </Button>
      )}
      <div style={viewerBoxStyle}>{formattedContent}</div>
    </div>
  );
}
