/**
 * Settings 相关类型定义
 */

export interface ConfigSection {
  name: string;
  data: Record<string, unknown>;
}

export interface ConfigResponse {
  sections: ConfigSection[];
}

export interface ConfigUpdateResponse {
  success: boolean;
  message: string;
}
