// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC721/extensions/ERC721URIStorage.sol";
import "@openzeppelin/contracts/token/common/ERC2981.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/Counters.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

contract IPRegistry is ERC721URIStorage, ERC2981, Ownable, ReentrancyGuard {
    using Counters for Counters.Counter;

    Counters.Counter private _tokenIds;
    Counters.Counter private _disputeIds;

    // ============ Core IP Asset ============
    struct IPAsset {
        uint256 tokenId;
        address creator;
        address currentOwner;
        string contentHash;
        string ipfsCID;
        string title;
        string description;
        string category;
        uint256 timestamp;
        bool isListed;
        uint256 price;
        uint96 royaltyFee; // basis points (e.g. 500 = 5%)
    }

    // ============ Licensing ============
    enum LicenseType { None, TimeLimited, QuantityLimited, Perpetual }

    struct License {
        uint256 licenseId;
        uint256 tokenId;
        address licensee;
        LicenseType licenseType;
        uint256 expiresAt;      // timestamp for time-limited
        uint256 maxUses;        // max uses for quantity-limited
        uint256 usedCount;      // current usage count
        uint256 price;
        bool active;
    }

    struct LicenseTemplate {
        LicenseType licenseType;
        uint256 duration;       // in seconds (0 if quantity-limited)
        uint256 maxUses;        // 0 if time-limited
        uint256 price;
        bool enabled;
    }

    // ============ DAO Dispute ============
    enum DisputeStatus { Open, Voting, Resolved, Dismissed }

    struct Dispute {
        uint256 disputeId;
        uint256 tokenId;
        address plaintiff;
        address defendant;
        string reason;
        DisputeStatus status;
        uint256 votesFor;
        uint256 votesAgainst;
        uint256 createdAt;
        uint256 resolvedAt;
        mapping(address => bool) hasVoted;
    }

    // ============ Mappings ============
    mapping(uint256 => IPAsset) public ipAssets;
    mapping(bytes32 => uint256) public hashToTokenId;
    mapping(address => uint256[]) public creatorTokens;
    mapping(uint256 => License[]) public assetLicenses;
    mapping(uint256 => LicenseTemplate) public licenseTemplates;
    mapping(uint256 => Dispute) public disputes;
    address[] public daoMembers;

    // ============ Events ============
    event IPRegistered(uint256 indexed tokenId, address indexed creator, string contentHash, string title, string category, uint256 timestamp);
    event IPListed(uint256 indexed tokenId, uint256 price);
    event IPPriceUpdated(uint256 indexed tokenId, uint256 newPrice);
    event IPUnlisted(uint256 indexed tokenId);
    event IPTransferred(uint256 indexed tokenId, address from, address to, uint256 price);
    event RoyaltySet(uint256 indexed tokenId, address recipient, uint96 fee);

    event LicenseCreated(uint256 indexed licenseId, uint256 indexed tokenId, address indexed licensee, LicenseType licenseType, uint256 expiresAt, uint256 maxUses, uint256 price);
    event LicenseUsed(uint256 indexed licenseId, uint256 indexed tokenId);
    event LicenseRevoked(uint256 indexed licenseId);

    event DisputeOpened(uint256 indexed disputeId, uint256 indexed tokenId, address plaintiff, string reason);
    event VoteCast(uint256 indexed disputeId, address voter, bool support);
    event DisputeResolved(uint256 indexed disputeId, bool plaintiffWon);

    constructor() ERC721("IPChain Registry", "IPR") Ownable(msg.sender) {}

    // ============ IP Registration ============
    function registerIP(string memory contentHash, string memory ipfsCID, string memory title, string memory description, string memory category, uint96 royaltyFee) public returns (uint256) {
        require(bytes(contentHash).length > 0, "Content hash required");
        require(bytes(title).length > 0, "Title required");
        require(royaltyFee <= 1000, "Royalty max 10%");

        bytes32 hashKey = keccak256(abi.encodePacked(contentHash));
        require(hashToTokenId[hashKey] == 0, "Content already registered");

        _tokenIds.increment();
        uint256 newTokenId = _tokenIds.current();
        _safeMint(msg.sender, newTokenId);

        ipAssets[newTokenId] = IPAsset(newTokenId, msg.sender, msg.sender, contentHash, ipfsCID, title, description, category, block.timestamp, false, 0, royaltyFee);
        hashToTokenId[hashKey] = newTokenId;
        creatorTokens[msg.sender].push(newTokenId);

        // Set ERC-2981 royalty
        _setTokenRoyalty(newTokenId, msg.sender, royaltyFee);

        emit IPRegistered(newTokenId, msg.sender, contentHash, title, category, block.timestamp);
        return newTokenId;
    }

    // ============ Marketplace ============
    function listIP(uint256 tokenId, uint256 price) public {
        require(ownerOf(tokenId) == msg.sender, "Not owner");
        require(price > 0, "Price must be > 0");
        require(!ipAssets[tokenId].isListed, "Already listed");
        ipAssets[tokenId].isListed = true;
        ipAssets[tokenId].price = price;
        emit IPListed(tokenId, price);
    }

    function updatePrice(uint256 tokenId, uint256 newPrice) public {
        require(ownerOf(tokenId) == msg.sender, "Not owner");
        require(ipAssets[tokenId].isListed, "Not listed");
        require(newPrice > 0, "Price must be > 0");
        ipAssets[tokenId].price = newPrice;
        emit IPPriceUpdated(tokenId, newPrice);
    }

    function unlistIP(uint256 tokenId) public {
        require(ownerOf(tokenId) == msg.sender, "Not owner");
        ipAssets[tokenId].isListed = false;
        ipAssets[tokenId].price = 0;
        emit IPUnlisted(tokenId);
    }

    function buyIP(uint256 tokenId) public payable nonReentrant {
        require(ipAssets[tokenId].isListed, "Not listed for sale");
        require(msg.value == ipAssets[tokenId].price, "Incorrect payment");
        require(msg.sender != ownerOf(tokenId), "Cannot buy own IP");

        address seller = ownerOf(tokenId);
        address creator = ipAssets[tokenId].creator;
        uint96 royaltyFee = ipAssets[tokenId].royaltyFee;

        ipAssets[tokenId].isListed = false;
        ipAssets[tokenId].price = 0;
        ipAssets[tokenId].currentOwner = msg.sender;

        // Distribute payment with royalty
        if (royaltyFee > 0 && seller != creator) {
            uint256 royaltyAmount = (msg.value * royaltyFee) / 10000;
            uint256 sellerAmount = msg.value - royaltyAmount;
            payable(creator).transfer(royaltyAmount);
            payable(seller).transfer(sellerAmount);
        } else {
            payable(seller).transfer(msg.value);
        }

        _transfer(seller, msg.sender, tokenId);
        emit IPTransferred(tokenId, seller, msg.sender, msg.value);
    }

    // ============ Licensing ============
    function setLicenseTemplate(uint256 templateId, LicenseType licenseType, uint256 duration, uint256 maxUses, uint256 price, bool enabled) public onlyOwner {
        licenseTemplates[templateId] = LicenseTemplate(licenseType, duration, maxUses, price, enabled);
    }

    function createLicense(uint256 tokenId, address licensee, uint256 templateId) public payable nonReentrant {
        require(ownerOf(tokenId) == msg.sender || msg.sender == licensee, "Unauthorized");
        LicenseTemplate storage tmpl = licenseTemplates[templateId];
        require(tmpl.enabled, "Template not enabled");
        require(msg.value == tmpl.price, "Incorrect payment");

        uint256 licenseId = assetLicenses[tokenId].length;
        uint256 expiresAt = 0;
        uint256 maxUses = 0;

        if (tmpl.licenseType == LicenseType.TimeLimited) {
            expiresAt = block.timestamp + tmpl.duration;
        } else if (tmpl.licenseType == LicenseType.QuantityLimited) {
            maxUses = tmpl.maxUses;
        }

        License memory lic = License(licenseId, tokenId, licensee, tmpl.licenseType, expiresAt, maxUses, 0, tmpl.price, true);
        assetLicenses[tokenId].push(lic);

        // Pay creator
        payable(ownerOf(tokenId)).transfer(msg.value);

        emit LicenseCreated(licenseId, tokenId, licensee, tmpl.licenseType, expiresAt, maxUses, tmpl.price);
    }

    function useLicense(uint256 tokenId, uint256 licenseId) public {
        License storage lic = assetLicenses[tokenId][licenseId];
        require(lic.active, "License not active");
        require(lic.licensee == msg.sender, "Not licensee");

        if (lic.licenseType == LicenseType.TimeLimited) {
            require(block.timestamp <= lic.expiresAt, "License expired");
        } else if (lic.licenseType == LicenseType.QuantityLimited) {
            require(lic.usedCount < lic.maxUses, "License usage exhausted");
        }

        lic.usedCount++;
        emit LicenseUsed(licenseId, tokenId);
    }

    function revokeLicense(uint256 tokenId, uint256 licenseId) public {
        require(ownerOf(tokenId) == msg.sender, "Not owner");
        assetLicenses[tokenId][licenseId].active = false;
        emit LicenseRevoked(licenseId);
    }

    function getAssetLicenses(uint256 tokenId) public view returns (License[] memory) {
        return assetLicenses[tokenId];
    }

    // ============ DAO Dispute Resolution ============
    function addDAOMember(address member) public onlyOwner {
        daoMembers.push(member);
    }

    function openDispute(uint256 tokenId, address defendant, string memory reason) public {
        require(ownerOf(tokenId) == msg.sender || ipAssets[tokenId].creator == msg.sender, "Not owner or creator");
        _disputeIds.increment();
        uint256 newId = _disputeIds.current();
        Dispute storage d = disputes[newId];
        d.disputeId = newId;
        d.tokenId = tokenId;
        d.plaintiff = msg.sender;
        d.defendant = defendant;
        d.reason = reason;
        d.status = DisputeStatus.Open;
        d.createdAt = block.timestamp;
        emit DisputeOpened(newId, tokenId, msg.sender, reason);
    }

    function castVote(uint256 disputeId, bool support) public {
        bool isMember = false;
        for (uint i = 0; i < daoMembers.length; i++) {
            if (daoMembers[i] == msg.sender) { isMember = true; break; }
        }
        require(isMember, "Not DAO member");
        Dispute storage d = disputes[disputeId];
        require(d.status == DisputeStatus.Open || d.status == DisputeStatus.Voting, "Not votable");
        require(!d.hasVoted[msg.sender], "Already voted");

        d.hasVoted[msg.sender] = true;
        d.status = DisputeStatus.Voting;

        if (support) {
            d.votesFor++;
        } else {
            d.votesAgainst++;
        }

        emit VoteCast(disputeId, msg.sender, support);

        // Auto-resolve if majority reached
        uint256 totalVotes = d.votesFor + d.votesAgainst;
        if (totalVotes >= daoMembers.length / 2) {
            resolveDispute(disputeId, d.votesFor > d.votesAgainst);
        }
    }

    function resolveDispute(uint256 disputeId, bool plaintiffWon) internal {
        Dispute storage d = disputes[disputeId];
        d.status = DisputeStatus.Resolved;
        d.resolvedAt = block.timestamp;

        if (plaintiffWon) {
            // Transfer NFT back to plaintiff
            address currentOwner = ownerOf(d.tokenId);
            if (currentOwner != d.plaintiff) {
                _transfer(currentOwner, d.plaintiff, d.tokenId);
            }
        }

        emit DisputeResolved(disputeId, plaintiffWon);
    }

    // ============ Verification ============
    function verifyContent(string memory contentHash) public view returns (bool registered, uint256 tokenId, address creator, uint256 timestamp) {
        bytes32 hashKey = keccak256(abi.encodePacked(contentHash));
        tokenId = hashToTokenId[hashKey];
        registered = tokenId > 0;
        if (registered) {
            creator = ipAssets[tokenId].creator;
            timestamp = ipAssets[tokenId].timestamp;
        }
    }

    // ============ Getters ============
    function getIPAsset(uint256 tokenId) public view returns (IPAsset memory) {
        require(ownerOf(tokenId) != address(0), "Token does not exist");
        return ipAssets[tokenId];
    }

    function getCreatorTokens(address creator) public view returns (uint256[] memory) {
        return creatorTokens[creator];
    }

    function getAllListed() public view returns (IPAsset[] memory) {
        uint256 total = _tokenIds.current();
        uint256 count = 0;
        for (uint256 i = 1; i <= total; i++) {
            if (ipAssets[i].isListed) count++;
        }
        IPAsset[] memory listed = new IPAsset[](count);
        uint256 idx = 0;
        for (uint256 i = 1; i <= total; i++) {
            if (ipAssets[i].isListed) {
                listed[idx] = ipAssets[i];
                idx++;
            }
        }
        return listed;
    }

    function totalSupply() public view returns (uint256) {
        return _tokenIds.current();
    }

    // ============ Overrides ============
    function supportsInterface(bytes4 interfaceId) public view virtual override(ERC721URIStorage, ERC2981) returns (bool) {
        return super.supportsInterface(interfaceId);
    }

    function _update(address to, uint256 tokenId, address auth) internal override(ERC721) returns (address) {
        return super._update(to, tokenId, auth);
    }

    function _increaseBalance(address account, uint128 value) internal override(ERC721) {
        super._increaseBalance(account, value);
    }
}