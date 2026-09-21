const form = document.querySelector('#login-form');
const message = document.querySelector('#login-message');

if (new URLSearchParams(window.location.search).has('error')) message.textContent = '비밀번호가 올바르지 않습니다.';

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  message.textContent = '';
  const button = form.querySelector('button');
  button.disabled = true;
  try {
    const response = await fetch('/admin/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ password: form.elements.namedItem('password').value }),
      credentials: 'same-origin',
    });
    if (response.ok) {
      window.location.assign('/admin/');
      return;
    }
    const data = await response.json().catch(() => null);
    message.textContent = data?.error?.message || `로그인에 실패했습니다. HTTP ${response.status}`;
  } catch {
    message.textContent = '서버에 연결하지 못했습니다.';
  } finally {
    button.disabled = false;
  }
});
