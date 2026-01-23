**`create_agent` 是支持图片传入的，但需要通过消息中的内容块（content blocks）来实现。**

`create_agent` 本身并不直接处理图片格式，而是通过标准的消息格式支持多模态输入。你需要在传递给 agent 的消息中包含图片内容块，底层模型会处理这些多模态数据。

## 如何在 create_agent 中传入图片

在调用 `agent.invoke()` 时，将图片作为消息内容的一部分传入：

```python
from langchain.agents import create_agent

agent = create_agent({
    model="gpt-4-vision",  # 使用支持多模态的模型
    tools=[your_tools],
    system_prompt="分析提供的图片内容"
})

# 从 URL 传入图片
result = await agent.invoke({
    "messages": [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "这张图片里有什么？"},
                {"type": "image", "url": "https://example.com/image.jpg"}
            ]
        }
    ]
})

# 或从 base64 编码传入图片
result = await agent.invoke({
    "messages": [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "描述这张图片"},
                {
                    "type": "image",
                    "base64": "AAAAIGZ0eXBtcDQyAAAAAGlzb21tcDQyAAACAGlzb2...",
                    "mime_type": "image/jpeg"
                }
            ]
        }
    ]
})
```

## 支持的多模态格式

LangChain 通过标准内容块支持多种多模态数据格式：

- **图片**：从 URL、base64 数据或文件 ID 传入
- **音频**：支持多种音频格式
- **文档**：如 PDF 文件
- **视频**：支持视频文件

## 重要前提条件

你选择的模型必须支持多模态输入。常见的支持模型包括：

- OpenAI 的 `gpt-4-vision` 或 `gpt-4-turbo`
- Anthropic 的 Claude 3 系列
- Google 的 Gemini Pro Vision

如果使用不支持多模态的模型，图片内容将被忽略或导致错误。

**Relevant docs:**

- [Messages - Multimodal content](https://docs.langchain.com/oss/python/langchain/messages#multimodal)
- [Models - Multimodal support](https://docs.langchain.com/oss/javascript/langchain/models#multimodal)
- [Standard content blocks overview](https://docs.langchain.com/oss/javascript/releases/langchain-v1#standard-content-blocks)