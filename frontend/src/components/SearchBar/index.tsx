import { useState, useEffect, useRef } from 'react';
import { Input, Dropdown, List, Typography, Empty, Spin } from 'antd';
import { SearchOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { search } from '@/api/search';
import { useDebounce } from '@/hooks/useDebounce';
import { ROUTES } from '@/constants/routes';

const { Text } = Typography;

interface SearchResult {
  type: string;
  id: string;
  title?: string;
  name?: string;
  content?: string;
  description?: string;
}

interface SearchData {
  todos?: SearchResult[];
  agents?: SearchResult[];
  workflows?: SearchResult[];
  wagents?: SearchResult[];
  tasks?: SearchResult[];
  messages?: SearchResult[];
}

const CATEGORY_LABELS: Record<string, string> = {
  todos: '待办',
  agents: 'Agent',
  tasks: '调度',
  messages: '消息',
};

const CATEGORY_ROUTES: Record<string, (id: string) => string> = {
  todos: () => ROUTES.TODOS,
  agents: (id) => `/config/agents/${id}`,
  tasks: () => ROUTES.SCHEDULING,
  messages: () => ROUTES.MESSAGES,
};

function getItemTitle(item: SearchResult): string {
  return item.title ?? item.name ?? item.content ?? item.id ?? '';
}

export default function SearchBar() {
  const [value, setValue] = useState('');
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<SearchData | null>(null);
  const debouncedValue = useDebounce(value, 300);
  const navigate = useNavigate();
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (value.trim()) setOpen(true);
    else setOpen(false);
  }, [value]);

  useEffect(() => {
    if (!debouncedValue.trim()) {
      setResults(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    search(debouncedValue)
      .then((res) => {
        const body = (res as { data: { data?: SearchData } }).data;
        const data = (body as { data?: SearchData })?.data ?? body;
        setResults((data as SearchData) ?? null);
      })
      .catch(() => setResults(null))
      .finally(() => setLoading(false));
  }, [debouncedValue]);

  const handleSelect = (type: keyof SearchData, item: SearchResult) => {
    const routeFn = CATEGORY_ROUTES[type];
    if (routeFn) {
      const path = routeFn(item.id);
      navigate(path);
      setOpen(false);
      setValue('');
    }
  };

  const categories = Object.entries(CATEGORY_LABELS);
  const hasResults =
    results &&
    Object.values(results).some(
      (arr) => Array.isArray(arr) && arr.length > 0
    );

  const dropdownContent = (
    <div
      ref={containerRef}
      style={{
        width: 400,
        maxHeight: 400,
        overflow: 'auto',
        background: '#fff',
        borderRadius: 8,
        boxShadow: '0 6px 16px rgba(0,0,0,0.08)',
        padding: 8,
      }}
    >
      {loading ? (
        <div style={{ padding: 24, textAlign: 'center' }}>
          <Spin />
        </div>
      ) : !debouncedValue.trim() ? (
        <Empty description="输入关键词搜索" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : !hasResults ? (
        <Empty description="未找到相关结果" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : (
        categories.map(([key, label]) => {
          const items = (results as SearchData)?.[key as keyof SearchData];
          if (!Array.isArray(items) || items.length === 0) return null;
          return (
            <div key={key} style={{ marginBottom: 12 }}>
              <Text type="secondary" style={{ fontSize: 12, marginBottom: 4, display: 'block' }}>
                {label}
              </Text>
              <List
                size="small"
                dataSource={items}
                renderItem={(item) => (
                  <List.Item
                    style={{ cursor: 'pointer', padding: '4px 8px' }}
                    onClick={() => handleSelect(key as keyof SearchData, item)}
                  >
                    <div style={{ width: '100%' }}>
                      <Text ellipsis>{getItemTitle(item)}</Text>
                      {item.description && (
                        <div>
                          <Text type="secondary" style={{ fontSize: 12 }} ellipsis>
                            {item.description}
                          </Text>
                        </div>
                      )}
                    </div>
                  </List.Item>
                )}
              />
            </div>
          );
        })
      )}
    </div>
  );

  return (
    <Dropdown
      open={open}
      onOpenChange={(open) => setOpen(open)}
      dropdownRender={() => dropdownContent}
      trigger={['click']}
    >
      <Input
        placeholder="搜索待办、Agent、调度..."
        prefix={<SearchOutlined />}
        style={{ width: 360 }}
        allowClear
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onFocus={() => value && setOpen(true)}
      />
    </Dropdown>
  );
}
