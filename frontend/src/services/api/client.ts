/**
 * Axios 客户端配置
 */

import axios from 'axios';

export const apiClient = axios.create({
  baseURL: '/api',
  timeout: 10000,
});
