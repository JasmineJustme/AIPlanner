import { useEffect, useState, useRef } from 'react';
import {
  Tabs,
  Card,
  Form,
  Select,
  Input,
  InputNumber,
  Slider,
  Button,
  message,
  Typography,
  Switch,
  Space,
  Tooltip,
  Alert,
  Tag,
  Collapse,
} from 'antd';
import {
  getLLMConfig,
  updateLLMConfig,
  testLLMConfig,
} from '@/api/config';

const { Title, Text } = Typography;

const PURPOSES = [
  { key: 'todo_analysis', label: '待办梳理 LLM' },
  { key: 'todo_dedup', label: '待办任务去重 LLM' },
  { key: 'orchestration', label: '智能编排 LLM' },
] as const;

const PROVIDER_OPTIONS = [
  { value: 'openai', label: 'OpenAI' },
  { value: 'azure', label: 'Azure' },
  { value: 'deepseek', label: 'DeepSeek' },
  { value: 'qwen', label: 'Qwen' },
  { value: 'dify', label: 'Dify' },
  { value: 'custom', label: 'Custom' },
];

const REQUIRED_ORCHESTRATION_PLACEHOLDERS = [
  '{current_time}',
  '{todo_desc}',
  '{agent_desc}',
  '{wagent_desc}',
  '{workflow_desc}',
] as const;

const REQUIRED_TODO_ANALYSIS_PLACEHOLDERS = [
  '{current_time}',
  '{datasource_info}',
  '{responsibilities}',
] as const;

const REQUIRED_TODO_DEDUP_PLACEHOLDERS = [
  '{current_time}',
  '{todo_desc}',
] as const;

const ORCHESTRATION_FIXED_JSON_OUTPUT_FORMAT = `请严格返回 JSON 对象，不要输出 Markdown 代码块，不要输出解释文本。\nJSON 必须包含以下字段：\n{\n  "plan_type": "agent | wagent | new_wagent",\n  "recommended_id": "推荐的 agent/wagent id，没有可留空字符串",\n  "recommended_name": "推荐名称",\n  "reason": "推荐原因",\n  "input_params": {"参数名": "参数值"},\n  "priority": "high | medium | low",\n  "estimated_duration_minutes": 30,\n  "start_time": "ISO8601 时间，例如 2026-03-09T09:00:00，必须结合当前时间判断，无法判断可用 null",\n  "deadline": "ISO8601 时间，例如 2026-03-09T18:00:00，需结合当前时间、预计时长和待办截止时间判断，无法判断可用 null",\n  "steps": [{"order": 1, "workflow_name": "步骤名"}]\n}`;

const TODO_ANALYSIS_FIXED_JSON_OUTPUT_FORMAT = `请严格返回 JSON 对象，不要输出 Markdown 代码块，不要输出解释文本。\nJSON 必须包含以下字段：\n{\n  "todos": [\n    {\n      "todo_summary": "待办摘要",\n      "task_description": "详细任务描述",\n      "priority": "high | medium | low",\n      "urgency_reason": "紧急性原因",\n      "start_recurring": false,\n      "confirm_by": null,\n      "executor": "user | system",\n      "tags": ["标签1", "标签2"],\n      "project": "项目名称",\n      "responsibility": "主要来源职责（字符串）",\n      "responsibilities": ["来源职责1", "来源职责2"]\n    }\n  ]\n}\n若没有可发掘待办，请返回 {"todos": []}。`;

const TODO_DEDUP_FIXED_JSON_OUTPUT_FORMAT = `请严格返回 JSON 对象，不要输出 Markdown 代码块，不要输出解释文本。\nJSON 必须包含以下字段：\n{\n  "dedup_results": [\n    {\n      "keep_id": "保留任务ID（输入中的 id）",\n      "remove_ids": ["需移除任务ID（输入中的 id）"],\n      "relation": "same | overlap | contains",\n      "reason": "去重理由"\n    }\n  ]\n}\n若无需去重，请返回 {"dedup_results": []}。`;

const ORCHESTRATION_PROMPT_EXAMPLE = `分析以下待办任务，从可用的Agent、W-Agent和Workflow中选择最佳方案来完成任务。\n\n当前时间：\n{current_time}\n\n待办任务：\n{todo_desc}\n\n可用Agent：\n{agent_desc}\n\n可用W-Agent：\n{wagent_desc}\n\n可用Workflow：\n{workflow_desc}\n\n要求：\n1. 结合任务描述和候选 input_params 自动补全最合适的 input_params。\n2. 必须结合上方“当前时间”为任务生成 start_time 与 deadline。\n3. deadline 不能晚于任务中最早的 due_date；如没有 due_date，请结合当前时间与 estimated_duration_minutes 给出合理 deadline。\n4. 若选择 new_wagent，请给出 steps；否则 steps 可为空数组。\n5. recommended_name 必须与 recommended_id 对应。`;

const TODO_ANALYSIS_PROMPT_EXAMPLE = `请根据数据源信息与工作职责，发掘潜在的待办任务。\n\n当前时间：\n{current_time}\n\n数据源信息：\n{datasource_info}\n\n工作职责：\n{responsibilities}\n\n要求：\n1. 输出必须与固定 JSON 结构一致。\n2. priority 仅可为 high / medium / low。\n3. 只输出可执行、可落地的待办。\n4. 若无待办则返回空数组。`;

const TODO_DEDUP_PROMPT_EXAMPLE = `请识别系统待办列表中的可去重关系（相同关系、重叠关系、包含关系），并直接输出去重结果。\n\n当前时间：\n{current_time}\n\n待办列表：\n{todo_desc}\n\n要求：\n1. 仅输出固定 JSON 结构。\n2. keep_id 必须是保留任务，remove_ids 是需要移除的任务。\n3. relation 仅可为 same / overlap / contains。\n4. 不确定时不要强行合并，返回空数组。`;

const PROMPT_TEMPLATE_ENHANCEMENT_CONFIG: Record<string, {
  requiredPlaceholders: readonly string[];
  labelHint: string;
  fixedJsonOutput: string;
  promptExample: string;
}> = {
  orchestration: {
    requiredPlaceholders: REQUIRED_ORCHESTRATION_PLACEHOLDERS,
    labelHint: '编排 prompt 必须预留指定字段',
    fixedJsonOutput: ORCHESTRATION_FIXED_JSON_OUTPUT_FORMAT,
    promptExample: ORCHESTRATION_PROMPT_EXAMPLE,
  },
  todo_analysis: {
    requiredPlaceholders: REQUIRED_TODO_ANALYSIS_PLACEHOLDERS,
    labelHint: '梳理 prompt 必须预留指定字段',
    fixedJsonOutput: TODO_ANALYSIS_FIXED_JSON_OUTPUT_FORMAT,
    promptExample: TODO_ANALYSIS_PROMPT_EXAMPLE,
  },
  todo_dedup: {
    requiredPlaceholders: REQUIRED_TODO_DEDUP_PLACEHOLDERS,
    labelHint: '去重 prompt 必须预留指定字段',
    fixedJsonOutput: TODO_DEDUP_FIXED_JSON_OUTPUT_FORMAT,
    promptExample: TODO_DEDUP_PROMPT_EXAMPLE,
  },
};

const buildPromptTemplateWithFixedPart = (editablePrompt: string, fixedPart: string) => {
  const body = (editablePrompt || '').trim();
  return body ? `${body}\n\n${fixedPart}` : fixedPart;
};

const stripLegacyFixedMarkers = (template: string) => template
  .replace(/^# ==== FIXED_JSON_OUTPUT_FORMAT_START \(DO NOT EDIT\) ====\s*\n?/gm, '')
  .replace(/^# ==== FIXED_JSON_OUTPUT_FORMAT_END ====\s*\n?/gm, '');

const splitPromptTemplateWithFixedPart = (fullTemplate: string, fallbackFixedPart: string) => {
  const raw = stripLegacyFixedMarkers(fullTemplate || '').trim();
  const fixedBlockAnchor = '请严格返回 JSON 对象，不要输出 Markdown 代码块，不要输出解释文本。';

  const anchorIdx = raw.indexOf(fixedBlockAnchor);
  if (anchorIdx !== -1) {
    const editablePrompt = raw.slice(0, anchorIdx).trimEnd();
    return { editablePrompt, fixedPart: fallbackFixedPart };
  }

  const fixedIdx = raw.indexOf(fallbackFixedPart);
  if (fixedIdx === -1) {
    return { editablePrompt: raw, fixedPart: fallbackFixedPart };
  }
  const editablePrompt = raw.slice(0, fixedIdx).trimEnd();
  const fixedPart = fallbackFixedPart;
  return { editablePrompt, fixedPart };
};

function LLMTab({
  purpose,
  label,
}: {
  purpose: string;
  label: string;
}) {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  // Add state for collapsibility and switches
  const [configExpanded, setConfigExpanded] = useState(true);
  const [useTemperature, setUseTemperature] = useState(true);
  const [useTopP, setUseTopP] = useState(true);
  const enhancementConfig = PROMPT_TEMPLATE_ENHANCEMENT_CONFIG[purpose];
  const isPromptTemplateEnhanced = !!enhancementConfig;
  const [fixedPromptPart, setFixedPromptPart] = useState(
    enhancementConfig?.fixedJsonOutput ?? ''
  );
  // Add ref to track notification state
  const notifiedRef = useRef(false);

  useEffect(() => {
      // Reset notification state when purpose changes
      notifiedRef.current = false;
  }, [purpose]);

  useEffect(() => {
    getLLMConfig(purpose)
      .then((res) => {
        const body = (res as { data: unknown }).data;
        const raw = (body as { data?: Record<string, unknown> })?.data ?? body;
        const config = raw as Record<string, unknown>;
        if (config && typeof config === 'object') {
          const isConfigured = !!(config.api_key && config.api_endpoint);

          if (!isConfigured && !notifiedRef.current) {
              message.info('模型尚未配置，请填写相应内容');
              notifiedRef.current = true;
          }
          setUseTemperature((config.temperature_enabled as boolean | undefined) ?? true);
          setUseTopP((config.top_p_enabled as boolean | undefined) ?? true);
          const savedPrompt = String(config.prompt_template ?? '');
          const splitPrompt = isPromptTemplateEnhanced
            ? splitPromptTemplateWithFixedPart(savedPrompt, enhancementConfig.fixedJsonOutput)
            : { editablePrompt: savedPrompt, fixedPart: '' };
          if (isPromptTemplateEnhanced) {
            setFixedPromptPart(splitPrompt.fixedPart || enhancementConfig.fixedJsonOutput);
          } else {
            setFixedPromptPart('');
          }
          form.setFieldsValue({
            provider: config.provider ?? 'openai',
            model_name: config.model_name ?? '',
            api_endpoint: config.api_endpoint ?? '',
            api_key: config.api_key ?? '',
            temperature: config.temperature ?? 0.7,
            top_p: config.top_p ?? 0.9,
            max_tokens: config.max_tokens ?? 4096,
            timeout: config.timeout ?? 180,
            prompt_template: splitPrompt.editablePrompt,
          });
        }
      })
      .catch(() => message.error('加载失败'));
  }, [purpose, form, isPromptTemplateEnhanced, enhancementConfig]);

  const buildPromptTemplatePayload = (editablePrompt: unknown) => {
    const raw = String(editablePrompt ?? '');
    return isPromptTemplateEnhanced
      ? buildPromptTemplateWithFixedPart(raw, fixedPromptPart || enhancementConfig.fixedJsonOutput)
      : raw;
  };

  const handleCopyFixedJsonBlock = async () => {
    if (!fixedPromptPart) {
      return;
    }
    try {
      await navigator.clipboard.writeText(fixedPromptPart);
      message.success('固定 JSON 区块已复制');
    } catch {
      message.error('复制失败，请手动复制');
    }
  };

  const buildPromptFieldErrorMessage = (detail: unknown) => {
    if (detail && typeof detail === 'object') {
      const obj = detail as {
        message?: string;
        missing_placeholders?: string[];
        unknown_placeholders?: string[];
        field?: string;
      };
      if (obj.field === 'prompt_template') {
        if (Array.isArray(obj.missing_placeholders) && obj.missing_placeholders.length > 0) {
          return `缺少占位符: ${obj.missing_placeholders.join(', ')}`;
        }
        if (Array.isArray(obj.unknown_placeholders) && obj.unknown_placeholders.length > 0) {
          return `存在未知占位符: ${obj.unknown_placeholders.join(', ')}`;
        }
        if (obj.message) {
          return obj.message;
        }
      }
    }
    const detailText = typeof detail === 'string' ? detail : '';
    if (detailText.includes('missing required placeholders')) {
      const found = detailText.match(/\{[^}]+\}/g);
      if (found && found.length > 0) {
        return `缺少占位符: ${found.join(', ')}`;
      }
      return detailText;
    }
    return '';
  };

  const onFinish = async (values: Record<string, unknown>) => {
    setLoading(true);
    try {
      await updateLLMConfig(purpose, {
        provider: values.provider,
        model_name: values.model_name,
        api_endpoint: values.api_endpoint,
        api_key: values.api_key,
        temperature: values.temperature,
        temperature_enabled: useTemperature,
        top_p: values.top_p,
        top_p_enabled: useTopP,
        max_tokens: values.max_tokens,
        timeout: values.timeout,
        prompt_template: buildPromptTemplatePayload(values.prompt_template),
      });
      form.setFields([{ name: 'prompt_template', errors: [] }]);
      message.success('保存成功');
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: unknown } }; message?: string };
      const promptError = buildPromptFieldErrorMessage(err?.response?.data?.detail);
      if (promptError) {
        form.setFields([{ name: 'prompt_template', errors: [promptError] }]);
        message.error(promptError);
      } else {
        message.error('保存失败');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleTest = async () => {
    try {
      // Validate form fields first
      const values = await form.validateFields();

      // If validation passes, we still need to save first or use current form values for testing if API supports it
      // Assuming testLLMConfig uses the saved config on backend, so we might want to save first?
      // Or if testLLMConfig just pings based on purpose, it relies on saved data.
      // Let's assume we need to save first to ensure test runs against latest input.

      // However, usually "Test" button sends current form values to a test endpoint
      // OR orchestrates a save-then-test flow.
      // Based on current API usage: testLLMConfig(purpose) likely tests the *saved* config.

      // Let's try to update first, then test, to ensure WYSIWYG
      await updateLLMConfig(purpose, {
        provider: values.provider,
        model_name: values.model_name,
        api_endpoint: values.api_endpoint,
        api_key: values.api_key,
        temperature: values.temperature,
        temperature_enabled: useTemperature,
        top_p: values.top_p,
        top_p_enabled: useTopP,
        max_tokens: values.max_tokens,
        timeout: values.timeout,
        prompt_template: buildPromptTemplatePayload(values.prompt_template),
      });

      await testLLMConfig(purpose);
      message.success('测试成功');
    } catch (e) {
      // Check if it's a validation error
      if (e && typeof e === 'object' && 'errorFields' in e) {
        message.error('请填写必填项');
        return;
      }

      // Check if it's an API error
      const err = e as { response?: { data?: { detail?: string } }; message?: string };
      const detail = err?.response?.data?.detail || err?.message || '测试失败';
      message.error(`测试失败: ${detail}`);
    }
  };

  return (
    <div>
      <Form
        form={form}
        layout="vertical"
        onFinish={onFinish}
        initialValues={{
          provider: 'openai',
          model_name: '',
          api_endpoint: '',
          api_key: '',
          temperature: 0.7,
          top_p: 0.9,
          max_tokens: 4096,
          timeout: 180,
          prompt_template: '',
        }}
      >
        <Card
          title={`${label} 配置`}
          style={{ marginBottom: 16 }}
          extra={
            <Space>
              <Button onClick={handleTest}>测试</Button>
              <Button onClick={() => setConfigExpanded(!configExpanded)}>
                {configExpanded ? '收起' : '展开'}
              </Button>
            </Space>
          }
          bodyStyle={{ display: configExpanded ? 'block' : 'none' }}
        >
            <Form.Item name="provider" label="Provider">
              <Select options={PROVIDER_OPTIONS} placeholder="选择 Provider" />
            </Form.Item>
            <Form.Item name="model_name" label="模型名称">
              <Input placeholder="如 gpt-4, gpt-3.5-turbo" />
            </Form.Item>
            <Form.Item
              name="api_endpoint"
              label="API Endpoint"
              rules={[{ required: true, message: '请输入 API Endpoint' }]}
            >
              <Input placeholder="https://api.openai.com/v1" />
            </Form.Item>
            <Form.Item
              name="api_key"
              label="API Key"
              rules={[{ required: true, message: '请输入 API Key' }]}
            >
              <Input.Password placeholder="API Key" />
            </Form.Item>
            <Form.Item
              label={
                <Space>
                  <span>Temperature</span>
                  <Switch
                    size="small"
                    checked={useTemperature}
                    onChange={setUseTemperature}
                  />
                </Space>
              }
              extra={useTemperature ? "0-2, 步长 0.1" : undefined}
            >
              {useTemperature ? (
                 <Form.Item name="temperature" noStyle>
                    <Slider min={0} max={2} step={0.1} />
                 </Form.Item>
              ) : null}
            </Form.Item>
            <Form.Item
              label={
                <Space>
                  <span>Top P</span>
                  <Switch
                    size="small"
                    checked={useTopP}
                    onChange={setUseTopP}
                  />
                </Space>
              }
              extra={useTopP ? "0-1" : undefined}
            >
              {useTopP ? (
                <Form.Item name="top_p" noStyle>
                  <Slider min={0} max={1} step={0.05} />
                </Form.Item>
              ) : null}
            </Form.Item>
            <Form.Item name="max_tokens" label="Max Tokens">
              <InputNumber min={1} max={128000} style={{ width: 120 }} />
            </Form.Item>
            <Form.Item
              name="timeout"
              label={
                <Space size={6}>
                  <span>超时时间（秒）</span>
                  <Tooltip title="LLM 请求的最大等待时间。超过该时间后请求将自动中断并提示超时。建议根据模型响应速度调整，默认 180 秒。">
                    <Text type="secondary" style={{ cursor: 'help' }}>(?)</Text>
                  </Tooltip>
                </Space>
              }
              extra="范围 1-600 秒，默认 180 秒"
            >
              <InputNumber min={1} max={600} step={1} style={{ width: 160 }} addonAfter="秒" />
            </Form.Item>
            <Form.Item
              name="prompt_template"
              label={
                <Space size={6}>
                  <span>Prompt 模板</span>
                  {isPromptTemplateEnhanced ? <Text type="warning">*</Text> : null}
                  {isPromptTemplateEnhanced ? (
                    <Tooltip title={enhancementConfig.labelHint}>
                      <Text type="secondary">(需预留字段)</Text>
                    </Tooltip>
                  ) : null}
                </Space>
              }
              rules={
                isPromptTemplateEnhanced
                  ? [
                      {
                        validator: async (_, value) => {
                          const fullTemplate = buildPromptTemplateWithFixedPart(
                            String(value ?? ''),
                            fixedPromptPart || enhancementConfig.fixedJsonOutput
                          );
                          const missed = enhancementConfig.requiredPlaceholders.filter(
                            (token) => !fullTemplate.includes(token)
                          );
                          if (missed.length > 0) {
                            throw new Error(`缺少占位符: ${missed.join(', ')}`);
                          }
                        },
                      },
                    ]
                  : undefined
              }
            >
              <Input.TextArea rows={10} placeholder="输入 prompt 模板可编辑部分" />
            </Form.Item>
            {isPromptTemplateEnhanced ? (
              <>
                <Space style={{ marginBottom: 8 }}>
                  <Tooltip title="CTRL + Z撤销填入">
                    <Button
                      size="small"
                      onClick={() => {
                        form.setFieldValue('prompt_template', enhancementConfig.promptExample);
                      }}
                    >
                      填入示例模版
                    </Button>
                  </Tooltip>
                  {enhancementConfig.requiredPlaceholders.map((token) => (
                    <Tag key={token}>{token}</Tag>
                  ))}
                </Space>
                <Collapse
                  items={[
                    {
                      key: 'fixed-json',
                      label: '固定 JSON 区块（只读）',
                      children: (
                        <>
                          <Alert
                            type="info"
                            showIcon
                            style={{ marginBottom: 8 }}
                            message="返回 JSON 格式为系统固定区块，不可在上方编辑框修改"
                          />
                          <Input.TextArea rows={12} value={fixedPromptPart} readOnly />
                          <Button size="small" style={{ marginTop: 8 }} onClick={handleCopyFixedJsonBlock}>
                            一键复制固定 JSON 区块
                          </Button>
                        </>
                      ),
                    },
                  ]}
                />
              </>
            ) : null}
            <Form.Item>
              <Button htmlType="submit" loading={loading}>
                保存
              </Button>
            </Form.Item>
        </Card>
      </Form>

    </div>
  );
}

export default function ConfigLLMPage() {
  return (
    <div>
      <Title level={3} style={{ marginBottom: 16 }}>
        大模型配置
      </Title>
      <Tabs
        items={PURPOSES.map(({ key, label }) => ({
          key,
          label,
          children: <LLMTab purpose={key} label={label} />,
        }))}
      />
    </div>
  );
}
