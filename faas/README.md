# Next.js 项目

这是一个基于 Next.js 的现代化 React 应用模板，支持服务端渲染和静态生成。

## 项目结构

项目结构：

```
├── app/           # Next.js 应用源码（App Router）
├── public/        # 静态资源目录
└── build/         # 构建输出目录（用于函数服务部署）
```

### 目录说明
- **app/** - Next.js 应用源码，使用 App Router 架构
- **public/** - 公共静态资源，如图片、图标等
- **build/** - 静态构建输出，用于函数服务托管

## 开发、构建和部署

### 1. 开发阶段

正常开发流程：
```bash
# 安装依赖
npm install

# 启动开发服务器
npm run dev
```

### 2. 构建阶段

开发完成后，构建生产版本：
```bash
# 运行构建脚本编译应用
./build.sh
```

### 3. 本地测试

构建完成后，本地测试：
```bash
./run.sh
```

### 4. 部署到函数服务

直接将这个代码包上传到 FaaS 平台即可

查看 [Next.js 部署文档](https://nextjs.org/docs/app/building-your-application/deploying) 了解更多详情。
