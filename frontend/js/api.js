// IP-Chain API Client
const API = (() => {
  const BASE_URL = 'http://localhost:3001/api';
  let authToken = localStorage.getItem('ipchain_token') || null;

  function getHeaders() {
    const h = { 'Content-Type': 'application/json' };
    if (authToken) h['Authorization'] = 'Bearer ' + authToken;
    return h;
  }

  async function request(method, path, body) {
    const opts = { method, headers: getHeaders() };
    if (body) opts.body = JSON.stringify(body);
    const res = await fetch(BASE_URL + path, opts);
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || data.message || 'Request failed');
    return data;
  }

  // Auth
  async function getNonce(address) {
    const data = await request('POST', '/auth/nonce', { address });
    return data.nonce;
  }
  async function verifyWallet(address, signature) {
    const data = await request('POST', '/auth/verify', { address, signature });
    if (data.token) { authToken = data.token; localStorage.setItem('ipchain_token', data.token); }
    return data;
  }
  function logout() { authToken = null; localStorage.removeItem('ipchain_token'); }
  function isAuthenticated() { return !!authToken; }
  function getToken() { return authToken; }

  // IP
  async function uploadIP(formData) {
    const h = {};
    if (authToken) h['Authorization'] = 'Bearer ' + authToken;
    const res = await fetch(BASE_URL + '/ip/upload', { method: 'POST', headers: h, body: formData });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || data.message || 'Upload failed');
    return data;
  }
  async function getMyIPs() { return request('GET', '/ip/my'); }
  async function getIPById(id) { return request('GET', '/ip/' + id); }
  async function mintIP(ipId, txHash, tokenId) {
    return request('POST', '/ip/' + ipId + '/mint', { txHash, tokenId });
  }

  // Market
  async function getListings(params) {
    const q = new URLSearchParams(params || {}).toString();
    return request('GET', '/market/listings' + (q ? '?' + q : ''));
  }
  async function listIP(ipId, price) {
    return request('POST', '/market/list', { ipId, price });
  }
  async function buyIP(listingId, txHash) {
    return request('POST', '/market/buy/' + listingId, { txHash });
  }
  async function getTransactions() { return request('GET', '/market/transactions'); }

  return {
    getNonce, verifyWallet, logout, isAuthenticated, getToken,
    uploadIP, getMyIPs, getIPById, mintIP,
    getListings, listIP, buyIP, getTransactions
  };
})();
