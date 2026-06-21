// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC721/extensions/ERC721URIStorage.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/Counters.sol";
import "@openzeppelin/contracts/utils/Strings.sol";

contract IPRegistry is ERC721URIStorage, Ownable {
    using Counters for Counters.Counter;
    using Strings for uint256;

    Counters.Counter private _tokenIds;

    struct IPAsset {
        uint256 tokenId;
        address creator;
        string contentHash;
        string ipfsCID;
        string title;
        string description;
        string category;
        uint256 timestamp;
        bool isListed;
        uint256 price;
    }

    mapping(uint256 => IPAsset) public ipAssets;
    mapping(bytes32 => uint256) public hashToTokenId;
    mapping(address => uint256[]) public creatorTokens;

    event IPRegistered(uint256 indexed tokenId, address indexed creator, string contentHash, string title, string category, uint256 timestamp);
    event IPListed(uint256 indexed tokenId, uint256 price);
    event IPPriceUpdated(uint256 indexed tokenId, uint256 newPrice);
    event IPUnlisted(uint256 indexed tokenId);
    event IPTransferred(uint256 indexed tokenId, address from, address to, uint256 price);

    constructor() ERC721("IPChain Registry", "IPR") Ownable(msg.sender) {}

    function registerIP(string memory contentHash, string memory ipfsCID, string memory title, string memory description, string memory category) public returns (uint256) {
        require(bytes(contentHash).length > 0, "Content hash required");
        require(bytes(title).length > 0, "Title required");

        bytes32 hashKey = keccak256(abi.encodePacked(contentHash));
        require(hashToTokenId[hashKey] == 0, "Content already registered");

        _tokenIds.increment();
        uint256 newTokenId = _tokenIds.current();

        _safeMint(msg.sender, newTokenId);

        ipAssets[newTokenId] = IPAsset(newTokenId, msg.sender, contentHash, ipfsCID, title, description, category, block.timestamp, false, 0);
        hashToTokenId[hashKey] = newTokenId;
        creatorTokens[msg.sender].push(newTokenId);

        emit IPRegistered(newTokenId, msg.sender, contentHash, title, category, block.timestamp);
        return newTokenId;
    }

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
        require(ipAssets[tokenId].isListed, "Not listed");
        ipAssets[tokenId].isListed = false;
        ipAssets[tokenId].price = 0;
        emit IPUnlisted(tokenId);
    }

    function buyIP(uint256 tokenId) public payable {
        require(ipAssets[tokenId].isListed, "Not listed for sale");
        require(msg.value == ipAssets[tokenId].price, "Incorrect payment");
        require(msg.sender != ownerOf(tokenId), "Cannot buy own IP");

        address seller = ownerOf(tokenId);
        ipAssets[tokenId].isListed = false;
        ipAssets[tokenId].price = 0;

        _transfer(seller, msg.sender, tokenId);
        payable(seller).transfer(msg.value);

        emit IPTransferred(tokenId, seller, msg.sender, msg.value);
    }

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
}