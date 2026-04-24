import type { App as AntdAppType } from 'antd';

let messageApi: AntdAppType['message'] | null = null;

export const setAntdMessageApi = (api: AntdAppType['message']) => {
  messageApi = api;
};

export const showMessageError = (content: string) => {
  messageApi?.error(content);
};

export const showMessageSuccess = (content: string) => {
  messageApi?.success(content);
};

export const showMessageInfo = (content: string) => {
  messageApi?.info(content);
};
