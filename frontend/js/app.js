// IP-Chain Main Application
const App = (() => {
  let state = {
    page: 'home',
    walletAddress: null,
    isConnected: false,
    isConnecting: false
  };

  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => document.querySelectorAll(sel);

  function navigateTo(page) {
    window.location.hash = page;
  }

  function getPageFromHash() {
    return window.location.hash.slice(1) || 'home';
  }

  async function loadPage(page) {
    const contentArea = $('#page-content');
    if (!contentArea || page === 'home') return;

    try {
      const res = await fetch('pages/' + page + '.html');
      if (!res.ok) throw new Error('Page not found');
      const html = await res.text();
      contentArea.innerHTML = html;
      // Re-execute scripts
      Array.from(contentArea.querySelectorAll('script')).forEach(oldScript => {
        const ns = document.createElement('script');
        Array.from(oldScript.attributes).forEach(a => ns.setAttribute(a.name, a.value));
        ns.textContent = oldScript.textContent;
        oldScript.parentNode.replaceChild(ns, oldScript);
      });
      initPageScripts(page);
    } catch (err) {
      contentArea.innerHTML = '<div class=\"empty-state\"><div class=\"empty-icon\">\ud83d\udcc4</div><h3>Page Not Found</h3><p>' + err.message + '</p></div>';
    }

    // Update active nav
    $$('.navbar-links a, .mobile-menu a').forEach(link => {
      link.classList.toggle('active', link.getAttribute('href') === '#' + page);
    });
    const mm = $('.mobile-menu');
    if (mm) mm.classList.remove('active');
  }

  function initPageScripts(page) {
    if (page === 'dashboard') initDashboard();
    else if (page === 'marketplace') initMarketplace();
    else if (page === 'upload') initUploadPage();
  }

  // Wallet
  async function connectWallet() {
    if (state.isConnecting) return;
    state.isConnecting = true;
    updateWalletUI();
    try {
      if (!window.ethereum) {
        showToast('Please install MetaMask to connect', 'warning');
        state.isConnecting = false; updateWalletUI(); return;
      }
      const accounts = await window.ethereum.request({ method: 'eth_requestAccounts' });
      const address = accounts[0];
      state.walletAddress = address;
      state.isConnected = true;
      state.isConnecting = false;
      try {
        const nonce = await API.getNonce(address);
        const msg = \"IP-Chain Authentication\\n\\nSign this message to verify ownership of\\n\" + address + \"\\n\\nNonce: \" + nonce;
        const signature = await window.ethereum.request({ method: 'personal_sign', params: [msg, address] });
        await API.verifyWallet(address, signature);
      } catch (e) { console.warn('Backend auth failed:', e); }
      updateWalletUI();
      showToast('Wallet connected: ' + shortenAddress(address), 'success');
    } catch (err) {
      state.isConnected = false; state.walletAddress = null; state.isConnecting = false;
      updateWalletUI();
      showToast('Failed to connect wallet', 'error');
    }
  }

  function disconnectWallet() {
    state.walletAddress = null; state.isConnected = false;
    API.logout();
    updateWalletUI();
    showToast('Wallet disconnected', 'info');
  }

  function shortenAddress(addr) {
    if (!addr) return '';
    return addr.slice(0, 6) + '...' + addr.slice(-4);
  }

  function updateWalletUI() {
    $$('.wallet-btn').forEach(btn => {
      if (state.isConnected && state.walletAddress) {
        btn.classList.add('connected');
        btn.innerHTML = '<span class=\"wallet-dot\"></span><span class=\"wallet-address\">' + shortenAddress(state.walletAddress) + '</span>';
        btn.onclick = disconnectWallet;
        btn.title = 'Click to disconnect';
      } else {
        btn.classList.remove('connected');
        btn.innerHTML = '<span class=\"wallet-dot\"></span>' + (state.isConnecting ? 'Connecting...' : 'Connect Wallet');
        btn.onclick = connectWallet;
        btn.title = 'Connect MetaMask';
      }
    });
  }

  // Toast
  function showToast(message, type) {
    type = type || 'info';
    let container = $('.toast-container');
    if (!container) {
      container = document.createElement('div');
      container.className = 'toast-container';
      document.body.appendChild(container);
    }
    const icons = { success: '\u2705', error: '\u274c', warning: '\u26a0\ufe0f', info: '\u2139\ufe0f' };
    const toast = document.createElement('div');
    toast.className = 'toast ' + type;
    toast.innerHTML = '<span class=\"toast-icon\">' + (icons[type] || '') + '</span><span class=\"toast-message\">' + message + '</span>';
    container.appendChild(toast);
    setTimeout(() => {
      toast.classList.add('toast-out');
      setTimeout(() => toast.remove(), 300);
    }, 4000);
  }

  // Dashboard
  async function initDashboard() {
    const grid = $('.ip-grid');
    const tbody = $('#txn-table-body');
    if (!grid) return;
    grid.innerHTML = '<div class=\"loading-container\"><div class=\"spinner spinner-lg\"></div><p>Loading your IP assets...</p></div>';
    try {
      const ips = await API.getMyIPs();
      renderIPGrid(grid, ips || []);
      if (tbody) {
        try {
          const txns = await API.getTransactions();
          renderTransactions(tbody, txns || []);
        } catch { tbody.innerHTML = '<tr><td colspan=\"4\" style=\"text-align:center;color:var(--text-muted)\">No transactions yet</td></tr>'; }
      }
      updateStats(ips || []);
    } catch (err) {
      grid.innerHTML = '<div class=\"empty-state\"><div class=\"empty-icon\">\u26a0\ufe0f</div><h3>Could not load assets</h3><p>' + err.message + '</p></div>';
    }
  }

  function renderIPGrid(container, items) {
    if (!items.length) {
      container.innerHTML = '<div class=\"empty-state\" style=\"grid-column:1/-1\"><div class=\"empty-icon\">\ud83c\udfa8</div><h3>No IP Assets Yet</h3><p>Upload your first creative work to protect it on the blockchain.</p><button class=\"btn btn-primary mt-3\" onclick=\"App.navigateTo('upload')\">Upload IP</button></div>';
      return;
    }
    const cats = { art:'Art', music:'Music', code:'Code', writing:'Writing', knowledge:'Knowledge' };
    container.innerHTML = items.map(item => {
      const cat = item.category || 'art';
      return '<div class=\"ip-card\">' +
        (item.thumbnail ? '<img class=\"ip-thumbnail\" src=\"' + item.thumbnail + '\" alt=\"' + item.title + '\">' :
          '<div class=\"ip-thumbnail-placeholder\">\ud83d\udcf1</div>') +
        '<div class=\"ip-info\"><span class=\"ip-category ' + cat + '\">' + (cats[cat] || cat) + '</span>' +
        '<h3 class=\"ip-title\">' + (item.title || 'Untitled') + '</h3>' +
        '<p class=\"ip-creator\">' + (item.tokenId ? 'Token #' + item.tokenId : 'Not minted') + '</p>' +
        '<div class=\"ip-price\">' + (item.price ? item.price + ' ETH' : '') + '</div></div></div>';
    }).join('');
  }

  function renderTransactions(tbody, txns) {
    if (!txns.length) {
      tbody.innerHTML = '<tr><td colspan=\"4\" style=\"text-align:center;color:var(--text-muted)\">No transactions yet</td></tr>';
      return;
    }
    tbody.innerHTML = txns.map(tx => {
      const sc = tx.status || 'pending';
      return '<tr><td class=\"txn-hash\">' + (tx.hash ? tx.hash.slice(0,10)+'...' : '-') + '</td><td>' + (tx.type || 'Transfer') + '</td><td>' + (tx.amount || '0') + ' ETH</td><td><span class=\"txn-status ' + sc + '\">' + sc + '</span></td></tr>';
    }).join('');
  }

  function updateStats(ips) {
    ['stat-value','stat-assets','stat-sold'].forEach(id => {
      const el = $('#' + id);
      if (id === 'stat-value') el && (el.textContent = ips.length > 0 ? (ips.length * 0.5).toFixed(1) + ' ETH' : '0 ETH');
      else if (id === 'stat-assets') el && (el.textContent = ips.length);
      else el && (el.textContent = ips.filter(i => i.sold).length || 0);
    });
  }

  // Marketplace
  let marketState = { items:[], filtered:[], category:'all', search:'', sort:'newest' };

  async function initMarketplace() {
    const grid = $('.ip-grid');
    if (!grid) return;
    grid.innerHTML = '<div class=\"loading-container\"><div class=\"spinner spinner-lg\"></div><p>Loading marketplace...</p></div>';
    try {
      let items = [];
      try { const data = await API.getListings(); items = data.listings || data || []; }
      catch {
        items = [
          { id:1, title:'Cosmic Dreamscape', category:'art', price:'2.5', creator:'0x742d...3a1b', thumbnail:'' },
          { id:2, title:'Synthwave Beats', category:'music', price:'1.2', creator:'0x8f3e...9c2d', thumbnail:'' },
          { id:3, title:'Smart Contract Lib', category:'code', price:'5.0', creator:'0x1a2b...4e5f', thumbnail:'' },
          { id:4, title:'The Art of Poetry', category:'writing', price:'0.8', creator:'0x9c4d...7e8f', thumbnail:'' },
          { id:5, title:'ML Fundamentals', category:'knowledge', price:'3.0', creator:'0x3b4c...5d6e', thumbnail:'' },
          { id:6, title:'Pixel Worlds', category:'art', price:'1.8', creator:'0x7d8e...9f0a', thumbnail:'' }
        ];
      }
      marketState.items = items; marketState.filtered = items;
      applyMarketFilters();
      renderMarketplace(grid);
      setupMarketListeners();
    } catch (err) {
      grid.innerHTML = '<div class=\"empty-state\"><div class=\"empty-icon\">\u26a0\ufe0f</div><h3>Could not load marketplace</h3><p>' + err.message + '</p></div>';
    }
  }

  function applyMarketFilters() {
    let items = [...marketState.items];
    if (marketState.category !== 'all') items = items.filter(i => i.category === marketState.category);
    if (marketState.search) {
      const q = marketState.search.toLowerCase();
      items = items.filter(i => (i.title||'').toLowerCase().includes(q) || (i.creator||'').toLowerCase().includes(q));
    }
    if (marketState.sort === 'price-low') items.sort((a,b) => parseFloat(a.price||0) - parseFloat(b.price||0));
    else if (marketState.sort === 'price-high') items.sort((a,b) => parseFloat(b.price||0) - parseFloat(a.price||0));
    else items.sort((a,b) => (b.id||0) - (a.id||0));
    marketState.filtered = items;
  }

  function renderMarketplace(grid) {
    if (!marketState.filtered.length) {
      grid.innerHTML = '<div class=\"empty-state\" style=\"grid-column:1/-1\"><div class=\"empty-icon\">\ud83d\uded2</div><h3>No Listings Found</h3><p>Try adjusting your search or filters.</p></div>';
      return;
    }
    const cats = { art:'Art', music:'Music', code:'Code', writing:'Writing', knowledge:'Knowledge' };
    grid.innerHTML = marketState.filtered.map(item => {
      const cat = item.category || 'art';
      const icons = { art:'\ud83d\uddbc', music:'\ud83c\udfb5', code:'\ud83d\udcbb', writing:'\ud83d\udcd6', knowledge:'\ud83d\udcda' };
      const thumb = item.thumbnail
        ? '<img class=\"ip-thumbnail\" src=\"' + item.thumbnail + '\" alt=\"' + item.title + '\">'
        : '<div class=\"ip-thumbnail-placeholder\">' + (icons[cat] || '\ud83d\udcf1') + '</div>';
      return '<div class=\"ip-card\">' + thumb +
        '<div class=\"ip-info\"><span class=\"ip-category ' + cat + '\">' + (cats[cat]||cat) + '</span>' +
        '<h3 class=\"ip-title\">' + (item.title||'Untitled') + '</h3>' +
        '<p class=\"ip-creator\">' + (item.creator ? item.creator.slice(0,8)+'...' : 'Unknown') + '</p></div>' +
        '<div class=\"ip-footer\"><span class=\"ip-price\">' + (item.price||'0') + ' ETH</span>' +
        '<button class=\"btn btn-primary btn-sm buy-btn\" data-id=\"" + (item.id||'') + "\" data-price=\"" + (item.price||'0') + "\">Buy Now</button></div></div>';
    }).join('');
  }

  function setupMarketListeners() {
    $$('.filter-btn').forEach(btn => {
      btn.onclick = () => {
        $$('.filter-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        marketState.category = btn.dataset.cat || 'all';
        applyMarketFilters();
        renderMarketplace($('.ip-grid'));
      };
    });
    const si = $('.search-box input');
    if (si) si.oninput = () => { marketState.search = si.value; applyMarketFilters(); renderMarketplace($('.ip-grid')); };
    const ss = $('.sort-select');
    if (ss) ss.onchange = () => { marketState.sort = ss.value; applyMarketFilters(); renderMarketplace($('.ip-grid')); };
    const grid = $('.ip-grid');
    if (grid) {
      grid.onclick = async (e) => {
        const btn = e.target.closest('.buy-btn');
        if (!btn) return;
        if (!state.isConnected) { showToast('Please connect your wallet first', 'warning'); return; }
        const price = btn.dataset.price;
        showToast('Processing purchase...', 'info');
        try {
          const pw = Blockchain.parseEther(price);
          const tx = await Blockchain.buyIPAsset(btn.dataset.id, pw);
          showToast('Transaction submitted! Confirming...', 'info');
          const receipt = await Blockchain.waitForTransaction(tx);
          await API.buyIP(btn.dataset.id, receipt.transactionHash);
          showToast('Purchase successful!', 'success');
          initMarketplace();
        } catch (err) { showToast('Purchase failed: ' + err.message, 'error'); }
      };
    }
  }

  // Upload
  async function initUploadPage() {
    const dz = $('.drop-zone');
    const fi = $('#file-input');
    const pv = $('#file-preview');
    const hd = $('#hash-display');
    const ub = $('#upload-btn');
    const mb = $('#mint-btn');
    const pf = $('.progress-fill');
    const pt = $('.progress-text');
    let selectedFile = null, fileHash = null, ipfsHash = null;

    if (dz && fi) {
      dz.onclick = () => fi.click();
      dz.ondragover = e => { e.preventDefault(); dz.classList.add('drag-over'); };
      dz.ondragleave = () => dz.classList.remove('drag-over');
      dz.ondrop = e => { e.preventDefault(); dz.classList.remove('drag-over'); if (e.dataTransfer.files.length) handleFile(e.dataTransfer.files[0]); };
      fi.onchange = () => { if (fi.files.length) handleFile(fi.files[0]); };
    }

    async function handleFile(file) {
      selectedFile = file;
      if (file.type.startsWith('image/')) {
        const reader = new FileReader();
        reader.onload = e => { pv.src = e.target.result; pv.style.display = 'block'; dz.querySelector('p').textContent = file.name; };
        reader.readAsDataURL(file);
      } else {
        pv.style.display = 'none';
        dz.querySelector('p').textContent = file.name;
      }
      const buf = await file.arrayBuffer();
      const hb = await crypto.subtle.digest('SHA-256', buf);
      const ha = Array.from(new Uint8Array(hb));
      fileHash = ha.map(b => b.toString(16).padStart(2,'0')).join('');
      if (hd) hd.textContent = fileHash;
    }

    const cb = $('.copy-btn');
    if (cb) cb.onclick = () => {
      if (fileHash) {
        navigator.clipboard.writeText(fileHash).then(() => showToast('Hash copied', 'success'))
          .catch(() => showToast('Could not copy', 'warning'));
      }
    };

    if (ub) ub.onclick = async () => {
      if (!selectedFile) { showToast('Please select a file', 'warning'); return; }
      const title = $('#ip-title').value.trim();
      if (!title) { showToast('Please enter a title', 'warning'); return; }
      ub.disabled = true; ub.textContent = 'Uploading...';
      if (pf) pf.style.width = '30%';
      if (pt) pt.textContent = 'Uploading to IPFS...';
      try {
        const fd = new FormData();
        fd.append('file', selectedFile);
        fd.append('title', title);
        fd.append('description', ($('#ip-desc').value || ''));
        fd.append('category', ($('#ip-category').value || 'art'));
        fd.append('hash', fileHash || '');
        const result = await API.uploadIP(fd);
        ipfsHash = result.ipfsHash || result.hash;
        if (pf) pf.style.width = '70%';
        if (pt) pt.textContent = 'Upload complete! Ready to mint.';
        showToast('File uploaded successfully!', 'success');
        if (mb) mb.disabled = false;
      } catch (err) { showToast('Upload failed: ' + err.message, 'error'); if (pf) pf.style.width = '0'; if (pt) pt.textContent = 'Upload failed'; }
      finally { ub.disabled = false; ub.textContent = 'Upload to IPFS'; }
    };

    if (mb) {
      mb.disabled = true;
      mb.onclick = async () => {
        if (!state.isConnected) { showToast('Connect wallet first', 'warning'); return; }
        if (!fileHash) { showToast('Upload a file first', 'warning'); return; }
        mb.disabled = true; mb.textContent = 'Minting...';
        if (pf) pf.style.width = '80%';
        if (pt) pt.textContent = 'Minting NFT on blockchain...';
        try {
          const mu = ipfsHash ? 'ipfs://' + ipfsHash : fileHash;
          const tx = await Blockchain.mintIPNFT(fileHash, mu);
          if (pt) pt.textContent = 'Waiting for confirmation...';
          const r = await Blockchain.waitForTransaction(tx);
          if (pf) pf.style.width = '100%';
          if (pt) pt.textContent = 'NFT Minted! Token ID: ' + (r.events?.[0]?.args?.tokenId?.toString() || 'N/A');
          showToast('NFT minted successfully!', 'success');
          try { await API.mintIP(r.events?.[0]?.args?.tokenId?.toString(), r.transactionHash); } catch {}
          mb.textContent = 'Minted!';
        } catch (err) { showToast('Minting failed: ' + err.message, 'error'); if (pf) pf.style.width = '70%'; if (pt) pt.textContent = 'Minting failed'; mb.disabled = false; mb.textContent = 'Mint NFT'; }
      };
    }
  }

  // Init
  function init() {
    window.addEventListener('scroll', () => {
      const n = $('.navbar');
      if (n) n.classList.toggle('scrolled', window.scrollY > 50);
    });
    const menuBtn = $('.mobile-menu-btn');
    const mobileMenu = $('.mobile-menu');
    if (menuBtn && mobileMenu) menuBtn.onclick = () => mobileMenu.classList.toggle('active');
    updateWalletUI();
    if (window.ethereum) {
      window.ethereum.on('accountsChanged', accounts => {
        if (!accounts.length) disconnectWallet();
        else if (accounts[0] !== state.walletAddress) { state.walletAddress = accounts[0]; state.isConnected = true; updateWalletUI(); }
      });
      window.ethereum.on('chainChanged', () => window.location.reload());
    }
    window.addEventListener('hashchange', () => { state.page = getPageFromHash(); loadPage(state.page); });
    state.page = getPageFromHash();
    loadPage(state.page);
  }

  return { init, navigateTo, connectWallet, disconnectWallet, showToast, shortenAddress, state };
})();
document.addEventListener('DOMContentLoaded', () => App.init());
