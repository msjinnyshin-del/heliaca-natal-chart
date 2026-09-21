import { buildInterpretationMarkdown } from './interpretation-export.js';

/** Clipboard is a user-initiated boundary; there is no external model request. */
export function mountInterpretationHandoff({ getCurrentExport, onMessage }) {
  const copyButton = document.querySelector('#copy-markdown');
  const previewButton = document.querySelector('#preview-markdown');
  const dialog = document.createElement('dialog');
  dialog.id = 'markdown-dialog';
  dialog.className = 'markdown-dialog';
  dialog.setAttribute('aria-labelledby', 'markdown-title');
  dialog.innerHTML = `
    <div class="markdown-dialog-heading"><div><p class="eyebrow">YOUR CHART, YOUR STORY</p><h2 id="markdown-title">해석용 Markdown</h2></div><button type="button" class="text-button" id="markdown-close" aria-label="미리보기 닫기">닫기 ×</button></div>
    <p>계산된 차트와 해석 요청문입니다. 출생 정보가 포함되어 있으니 확인 후 ChatGPT에 직접 붙여넣으세요. 자동 전송하지 않습니다.</p>
    <label for="markdown-content" class="eyebrow">COPY / PASTE INTO CHATGPT</label>
    <textarea id="markdown-content" readonly spellcheck="false" aria-label="해석용 Markdown 내용"></textarea>
    <p id="markdown-status" role="status" aria-live="polite"></p>
    <div class="markdown-dialog-actions"><button type="button" class="text-button" id="markdown-copy-again">복사</button><button type="button" class="text-button" id="markdown-select-all">전체 선택</button><button type="button" class="text-button" id="download-markdown">.md 저장</button><a id="open-chatgpt" href="https://chatgpt.com/" target="_blank" rel="noopener noreferrer" class="text-button">ChatGPT 열기 ↗</a></div>
  `;
  document.body.append(dialog);
  const textarea = dialog.querySelector('#markdown-content');
  const status = dialog.querySelector('#markdown-status');
  const retry = dialog.querySelector('#markdown-copy-again');
  let available = false;
  let revision = 0;
  let documentDate = '';

  function documentSnapshot() {
    const data = available ? getCurrentExport() : null;
    if (!data) throw new Error('현재 입력으로 다시 계산한 후 복사해 주세요.');
    return { text: buildInterpretationMarkdown(data.chart, {name: data.name}), date: data.payload.date };
  }

  function showPreview(snapshot) {
    textarea.value = snapshot.text;
    documentDate = snapshot.date;
    status.textContent = '';
    if (!dialog.open) dialog.showModal();
  }

  function announce(text, type) {
    onMessage(text, type);
    status.textContent = text;
  }

  async function copy() {
    const requestRevision = revision;
    let snapshot;
    try {
      snapshot = documentSnapshot();
    } catch (error) {
      announce(error.message, 'error');
      return;
    }
    copyButton.disabled = true;
    retry.disabled = true;
    try {
      if (!navigator.clipboard?.writeText) throw new Error('Clipboard API unavailable');
      await navigator.clipboard.writeText(snapshot.text);
      if (revision !== requestRevision) return;
      announce('해석용 Markdown을 복사했습니다. ChatGPT에 붙여넣어 해석을 요청하세요.', 'info');
    } catch {
      if (revision !== requestRevision) return;
      showPreview(snapshot);
      textarea.focus();
      textarea.select();
      announce('브라우저가 자동 복사를 허용하지 않았습니다. 선택된 내용을 ⌘C / Ctrl+C로 복사하거나 .md로 저장하세요.', 'info');
    } finally {
      if (revision === requestRevision) {
        copyButton.disabled = !available;
        retry.disabled = !available;
      }
    }
  }

  copyButton.addEventListener('click', copy);
  retry.addEventListener('click', copy);
  previewButton.addEventListener('click', () => {
    try { showPreview(documentSnapshot()); } catch (error) { announce(error.message, 'error'); }
  });
  dialog.querySelector('#markdown-close').addEventListener('click', () => dialog.close());
  dialog.querySelector('#markdown-select-all').addEventListener('click', () => {
    textarea.focus();
    textarea.select();
    status.textContent = '전체 선택했습니다. ⌘C / Ctrl+C로 복사하세요.';
  });
  dialog.querySelector('#download-markdown').addEventListener('click', () => {
    if (!available || !getCurrentExport() || !textarea.value) return;
    const url = URL.createObjectURL(new Blob([textarea.value], {type: 'text/markdown;charset=utf-8'}));
    const link = document.createElement('a');
    link.href = url;
    link.download = `natal-interpretation-${documentDate}.md`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });

  return {
    setAvailable(value) {
      available = Boolean(value);
      revision += 1;
      copyButton.disabled = !available;
      previewButton.disabled = !available;
      retry.disabled = !available;
      if (dialog.open) dialog.close();
      textarea.value = '';
      status.textContent = '';
    },
  };
}
