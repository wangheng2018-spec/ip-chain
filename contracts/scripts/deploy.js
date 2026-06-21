const hre = require("hardhat");

async function main() {
  console.log("Deploying IPRegistry...");
  const IPRegistry = await hre.ethers.getContractFactory("IPRegistry");
  const contract = await IPRegistry.deploy();
  await contract.waitForDeployment();
  const address = await contract.getAddress();
  console.log("IPRegistry deployed to:", address);
  if (hre.network.name !== "hardhat") {
    console.log("Verifying contract...");
    await hre.run("verify:verify", { address });
  }
}
main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});