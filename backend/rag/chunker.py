from langchain_text_splitters import RecursiveCharacterTextSplitter


def chunk_text(text: str, chunk_size: int = 512, overlap: int = 64) -> list[str]:
    """
    Split raw chat log into overlapping chunks.
    For chat logs, preserve line structure where possible.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=overlap,
        separators=["\n\n", "\n", "。", ".", "！", "!", "？", "?", " ", ""],
    )
    return splitter.split_text(text)


def parse_chat_log(raw_text: str) -> list[dict]:
    """
    Parse a WeChat/QQ-style chat log and extract messages.

    Expected format (WeChat export):
    2024-01-01 12:00 用户名
    message text
    """
    import re
    lines = raw_text.split("\n")
    messages = []
    current_sender = None
    current_msg = []

    header_pattern = re.compile(
        r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}\s+\d{1,2}:\d{2}(?::\d{2})?\s+(.+)"
    )

    for line in lines:
        m = header_pattern.match(line.strip())
        if m:
            if current_msg and current_sender:
                messages.append({
                    "sender": current_sender.strip(),
                    "content": "\n".join(current_msg).strip(),
                })
            current_sender = m.group(1)
            current_msg = []
        else:
            if line.strip():
                current_msg.append(line.strip())

    if current_msg and current_sender:
        messages.append({
            "sender": current_sender.strip(),
            "content": "\n".join(current_msg).strip(),
        })

    return messages


def extract_target_only(raw_text: str, target_name: str) -> str:
    """
    Extract only the target person's messages for embedding.
    """
    all_msgs = parse_chat_log(raw_text)
    target_msgs = [m["content"] for m in all_msgs if m["sender"] == target_name]
    return "\n\n".join(target_msgs)
