// IP-Chain Blockchain Utilities
const Blockchain = (() => {
  const CONFIG = {
    contractAddress: '0x0000000000000000000000000000000000000000',
    contractABI: [
      "function registerIP(string memory ipHash, string memory metadataURI) public returns (uint256)",
      "function listIP(uint256 tokenId, uint256 price) public",
      "function buyIP(uint256 listingId) public payable",
      "function getIPDetails(uint256 tokenId) public view returns (address creator, string memory ipHash, string memory metadataURI, uint256 timestamp)",
      "function getListing(uint256 listingId) public view returns (uint256 tokenId, address seller, uint256 price, bool active)",
      "function totalSupply() public view returns (uint256)",
      "event IPRegistered(uint256 indexed tokenId, address indexed creator, string ipHash)",
      "event IPListed(uint256 indexed listingId, uint256 indexed tokenId, address indexed seller, uint256 price)",
      "event IPTransferred(uint256 indexed listingId, uint256 indexed tokenId, address indexed buyer, address seller, uint256 price)"
    ]
  };

  let contract = null;
  let signer = null;
  let provider = null;

  async function initContract() {
    if (typeof window.ethereum === 'undefined') {
      throw new Error('MetaMask not detected. Please install MetaMask.');
    }
    provider = new ethers.providers.Web3Provider(window.ethereum);
    signer = provider.getSigner();
    contract = new ethers.Contract(CONFIG.contractAddress, CONFIG.contractABI, signer);
    return contract;
  }

  async function getContract() {
    if (!contract) await initContract();
    return contract;
  }

  async function getSigner() {
    if (!signer) await initContract();
    return signer;
  }

  async function getProvider() {
    if (!provider) await initContract();
    return provider;
  }

  async function getAccount() {
    if (!signer) await initContract();
    const accounts = await window.ethereum.request({ method: 'eth_requestAccounts' });
    return accounts[0];
  }

  async function mintIPNFT(ipHash, metadataURI) {
    const c = await getContract();
    const tx = await c.registerIP(ipHash, metadataURI);
    return tx;
  }

  async function listIPForSale(tokenId, priceWei) {
    const c = await getContract();
    const tx = await c.listIP(tokenId, priceWei);
    return tx;
  }

  async function buyIPAsset(listingId, priceWei) {
    const c = await getContract();
    const tx = await c.buyIP(listingId, { value: priceWei });
    return tx;
  }

  async function getIPDetails(tokenId) {
    const c = await getContract();
    return c.getIPDetails(tokenId);
  }

  async function waitForTransaction(tx) {
    const receipt = await tx.wait();
    return receipt;
  }

  function formatEther(wei) {
    return ethers.utils.formatEther(wei);
  }

  function parseEther(eth) {
    return ethers.utils.parseEther(eth.toString());
  }

  function isMetaMaskInstalled() {
    return typeof window.ethereum !== 'undefined';
  }

  return {
    initContract, getContract, getSigner, getProvider, getAccount,
    mintIPNFT, listIPForSale, buyIPAsset, getIPDetails,
    waitForTransaction, formatEther, parseEther, isMetaMaskInstalled,
    CONFIG
  };
})();
