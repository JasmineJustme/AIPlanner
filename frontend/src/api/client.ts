import axios from 'axios';
import type { AxiosInstance, AxiosResponse, InternalAxiosRequestConfig } from 'axios';
import { message } from 'antd';

export interface APIResponse<T = unknown> {
  code: number;
  message: string;
  data: T;
}

const ERROR_TOAST_DEDUP_MS = 1200;
let lastErrorToastText = '';
let lastErrorToastAt = 0;

const showErrorToast = (text: string) => {
  const now = Date.now();
  if (text === lastErrorToastText && now - lastErrorToastAt < ERROR_TOAST_DEDUP_MS) {
    return;
  }
  lastErrorToastText = text;
  lastErrorToastAt = now;
  message.error(text);
};

const client: AxiosInstance = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

client.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => config,
  (error) => Promise.reject(error),
);

client.interceptors.response.use(
  (response: AxiosResponse<APIResponse | Blob>) => {
    if (response.config.responseType === 'blob') {
      return response;
    }
    const { data } = response;
    if (data && typeof data === 'object' && 'code' in data && (data as APIResponse).code !== 200) {
      showErrorToast((data as APIResponse).message || '请求失败');
      return Promise.reject(new Error((data as APIResponse).message));
    }
    return response;
  },
  (error) => {
    if (error.response) {
      const status = error.response.status;
      if (status === 404) {
        showErrorToast('请求的资源不存在');
      } else if (status === 500) {
        showErrorToast('服务器内部错误');
      } else {
        showErrorToast(error.response.data?.message || '请求失败');
      }
    } else if (error.code === 'ECONNABORTED') {
      showErrorToast('请求超时，请重试');
    } else {
      showErrorToast('网络连接失败，请检查');
    }
    return Promise.reject(error);
  },
);

export default client;
