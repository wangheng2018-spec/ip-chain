const hre = require("hardhat");

async function main() {
  const network = hre.network.name;
  console.log("Deploying IPRegistry to:", network);

  const IPRegistry = await hre.ethers.getContractFactory("IPRegistry");
  const contract = await IPRegistry.deploy();
  await contract.waitForDeployment();

  const address = await contract.getAddress();
  console.log("IPRegistry deployed to:", address);

  // Save deployment address
  const fs = require("fs");
  const deployment = { network, address, timestamp: new Date().toISOString() };
  fs.writeFileSync("deployment.json", JSON.stringify(deployment, null, 2));
  console.log("Deployment saved to deployment.json");

  // Verify on Polygonscan (not for local hardhat)
  if (network !== "hardhat") {
    console.log("Verifying contract on Polygonscan...");
    try {
      await hre.run("verify:verify", { address, constructorArguments: [] });
      console.log("Contract verified!");
    } catch (e) {
      console.log("Verification error (may already be verified):", e.message);
    }
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});