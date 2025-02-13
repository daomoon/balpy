# balpy.py

# python basics
import json
import os
import requests
import time
import sys
import pkgutil

# web3 
from web3 import Web3
import eth_abi

# globals
global web3
global lastEtherscanCallTime
global etherscanMaxRate
global etherscanApiKey

class balpy(object):
	
	"""
	Balancer Protocol Python API
	Interface with Balancer V2 Smart contracts directly from Python
	"""

	# Contract addresses -- same across mainnet and testnets
	VAULT =                  			'0xBA12222222228d8Ba445958a75a0704d566BF2C8';
	WEIGHTED_POOL_FACTORY =  			'0x8E9aa87E45e92bad84D5F8DD1bff34Fb92637dE9';
	WEIGHTED_POOL_2_TOKENS_FACTORY =	'0xA5bf2ddF098bb0Ef6d120C98217dD6B141c74EE0';
	STABLE_POOL_FACTORY =				'0xA9B3f46761F3A47056F39724FB5D9560f3629fB8';
	DELEGATE_OWNER =         			'0xBA1BA1ba1BA1bA1bA1Ba1BA1ba1BA1bA1ba1ba1B';
	ZERO_ADDRESS =           			'0x0000000000000000000000000000000000000000';

	# Constants
	INFINITE = 2 ** 256 - 1; #for infinite unlock

	# Environment variable names
	envVarEtherscan = 	"KEY_API_ETHERSCAN";
	envVarInfura = 		"KEY_API_INFURA";
	envVarPrivate = 	"KEY_PRIVATE";
	envVarCustomRPC = 	"BALPY_CUSTOM_RPC";
	
	# Etherscan API call management	
	lastEtherscanCallTime = 0;
	etherscanMaxRate = 5.0; #hz
	etherscanSpeedDict = {
			"slow":"SafeGasPrice",
			"average":"ProposeGasPrice",
			"fast":"FastGasPrice"
	};

	# Network parameters
	networkParams = {	"mainnet":	{"id":1,	"etherscanURL":"etherscan.io"},
						"kovan":	{"id":42,	"etherscanURL":"kovan.etherscan.io"},
						"polygon":	{"id":137,	"etherscanURL":"polygonscan.com"}};

	# ABIs, Artifacts
	abis = {};
	artifacts = [	"Vault",
					"WeightedPoolFactory",
					"WeightedPool2TokensFactory",
					"StablePoolFactory"
				];
	contractAddresses = {	"Vault":VAULT,
							"WeightedPoolFactory":WEIGHTED_POOL_FACTORY,
							"WeightedPool2TokensFactory":WEIGHTED_POOL_2_TOKENS_FACTORY,
							"StablePoolFactory":STABLE_POOL_FACTORY
						};
	
	decimals = {};
	erc20Contracts = {};

	def __init__(self, network=None, verbose=True):
		super(balpy, self).__init__();

		self.verbose = verbose;
		if self.verbose:
			print();
			print("==============================================================");
			print("============== Initializing Balancer Python API ==============");
			print("==============================================================");
			print();

		if network is None:
			print("No network set. Defaulting to kovan");
			network = "kovan";
		else:
			print("Network is set to", network);

		self.infuraApiKey = 		os.environ.get(self.envVarInfura);
		self.customRPC = 			os.environ.get(self.envVarCustomRPC);
		self.etherscanApiKey = 		os.environ.get(self.envVarEtherscan);
		self.privateKey =  			os.environ.get(self.envVarPrivate);

		if self.infuraApiKey is None and self.customRPC is None:
			self.ERROR("You need to add your infuraApiKey or customRPC environment variables");
			print("\t\texport " + self.envVarInfura + "=<yourInfuraApiKey>");
			print("\t\t\tOR")
			print("\t\texport " + self.envVarCustomRPC + "=<yourCustomRPC>");
			print("\n\t\tNOTE: if you set " + self.envVarCustomRPC + ", it will override your Infura API key!")
			quit();

		if self.etherscanApiKey is None or self.privateKey is None:
			self.ERROR("You need to add your keys to the your environment variables");
			print("\t\texport " + self.envVarEtherscan + "=<yourEtherscanApiKey>");
			print("\t\texport " + self.envVarPrivate + "=<yourPrivateKey>");
			quit();

		self.network = network;
		endpoint = self.customRPC;
		if endpoint is None:
			endpoint = 'https://' + self.network + '.infura.io/v3/' + self.infuraApiKey;

		self.web3 = Web3(Web3.HTTPProvider(endpoint));
		acct = self.web3.eth.account.privateKeyToAccount(self.privateKey);
		self.web3.eth.default_account = acct.address;
		self.address = acct.address;

		if self.verbose:
			print("Initialized account", self.web3.eth.default_account);
			print("Connected to web3 at", endpoint);

		# Read files packaged in module
		for name in self.artifacts:
			artifactPath = os.path.join('artifacts/', self.network, name + '.json');
			f = pkgutil.get_data(__name__, artifactPath).decode();
			self.abis[name] = json.loads(f)["abi"];

	# ======================
	# ====Color Printing====
	# ======================
	def WARNING(self, text):
		WARNING_BEGIN = '\033[93m';
		WARNING_END = '\033[0m';
		print(WARNING_BEGIN + "[WARNING] " + text + WARNING_END);

	def ERROR(self, text):
		ERROR_BEGIN = '\033[91m';
		ERROR_END = '\033[0m';
		print(ERROR_BEGIN + "[ERROR] " + text + ERROR_END);

	# =====================
	# ===Transaction Fns===
	# =====================
	def buildTx(self, fn, gasFactor, gasSpeed="average", nonceOverride=-1, gasEstimateOverride=-1, gasPriceGweiOverride=-1):
		chainIdNetwork = self.networkParams[self.network]["id"];

		# Get nonce if not overridden
		if nonceOverride > -1:
			nonce = nonceOverride;
		else:
			nonce = self.web3.eth.get_transaction_count(self.web3.eth.default_account)

		# Calculate gas estimate if not overridden
		if gasEstimateOverride > -1:
			gasEstimate = gasEstimateOverride;
		else:
			gasEstimate = int(fn.estimateGas() * gasFactor);

		# Get gas price from Etherscan if not overridden
		if gasPriceGweiOverride > -1:
			gasPriceGwei = gasPriceGweiOverride;
		else:
			if not chainIdNetwork == 1: #if not mainnet
				gasPriceGwei = 5;
				pass;
			gasPriceGwei = self.getGasPriceEtherscanGwei(gasSpeed);
		
		print("Gas Estimate:\t", gasEstimate);
		print("Gas Price:\t", gasPriceGwei, "Gwei");
		print("Nonce:\t\t", nonce);

		# build transaction
		data = fn.buildTransaction({'chainId': chainIdNetwork,
								    'gas': gasEstimate,
								    'gasPrice': self.web3.toWei(gasPriceGwei, 'gwei'),
								    'nonce': nonce,
									});
		return(data);

	def sendTx(self, tx, isAsync=False):
		signedTx = self.web3.eth.account.sign_transaction(tx, self.privateKey);
		txHash = self.web3.eth.send_raw_transaction(signedTx.rawTransaction).hex();

		print("Sending transaction, view progress at:");
		print("\thttps://"+self.networkParams[self.network]["etherscanURL"]+"/tx/"+txHash);
		
		if not isAsync:
			self.waitForTx(txHash);
		return(txHash);

	def waitForTx(self, txHash, timeOutSec=120):
		print("Waiting for tx:", txHash);
		self.web3.eth.wait_for_transaction_receipt(txHash);
		print("\tTransaction accepted by network!\n");
		return(True);

	def getTxReceipt(self, txHash, delay, maxRetries):
		for i in range(maxRetries):
			try: 
				receipt = self.web3.eth.getTransactionReceipt(txHash);
				print("Retrieved receipt!");
				return(receipt);
			except Exception as e:
				print(e);
				print("Transaction not found yet, will check again in", delay, "seconds");
				time.sleep(delay);
		self.ERROR("Transaction not found in", maxRetries, "retries.");
		return(False);


	# =====================
	# ====ERC20 methods====
	# =====================
	def erc20GetContract(self, tokenAddress):
		# Check to see if contract is already in cache
		if tokenAddress in self.erc20Contracts.keys():
			return(self.erc20Contracts[tokenAddress]);

		# Read files packaged in module
		abiPath = os.path.join('abi/ERC20.json');
		f = pkgutil.get_data(__name__, abiPath).decode();
		abi = json.loads(f);
		token = self.web3.eth.contract(tokenAddress, abi=abi)
		self.erc20Contracts[tokenAddress] = token;
		return(token);

	def erc20GetDecimals(self, tokenAddress):
		if tokenAddress in self.decimals.keys():
			return(self.decimals[tokenAddress]);
		token = self.erc20GetContract(tokenAddress);
		decimals = token.functions.decimals().call();
		self.decimals[tokenAddress] = decimals;
		return(decimals);

	def erc20GetBalanceStandard(self, tokenAddress):
		token = self.erc20GetContract(tokenAddress);
		decimals = self.erc20GetDecimals(tokenAddress);
		standardBalance = token.functions.balanceOf(self.address).call() * 10**(-decimals);
		return(standardBalance);

	def erc20GetAllowanceStandard(self, tokenAddress, allowedAddress):
		token = self.erc20GetContract(tokenAddress);
		decimals = self.erc20GetDecimals(tokenAddress);
		standardAllowance = token.functions.allowance(self.address,allowedAddress).call() * 10**(-decimals);
		return(standardAllowance);

	def erc20BuildFunctionSetAllowance(self, tokenAddress, allowedAddress, allowance):
		token = self.erc20GetContract(tokenAddress);
		approveFunction = token.functions.approve(allowedAddress, allowance);
		return(approveFunction);

	def erc20SignAndSendNewAllowance(	self,
										tokenAddress, 
										allowedAddress, 
										allowance,
										gasFactor,
										gasSpeed,
										nonceOverride=-1, 
										gasEstimateOverride=-1, 
										gasPriceGweiOverride=-1,
										isAsync=False):
		fn = self.erc20BuildFunctionSetAllowance(tokenAddress, allowedAddress, allowance);
		tx = self.buildTx(fn, gasFactor, gasSpeed, nonceOverride, gasEstimateOverride, gasPriceGweiOverride);
		txHash = self.sendTx(tx, isAsync);
		return(txHash);

	def erc20HasSufficientBalance(self, tokenAddress, amountToUse):
		balance = self.erc20GetBalanceStandard(tokenAddress);

		print("Token:", tokenAddress);
		print("\tNeed:", float(amountToUse));
		print("\tWallet has:", float(balance));

		sufficient = (float(balance) >= float(amountToUse));
		if not sufficient:
			self.ERROR("Insufficient Balance!");
		else:
			print("\tWallet has sufficient balance.");
		print();
		return(sufficient);
	
	def erc20HasSufficientBalances(self, tokens, amounts):
		if not len(tokens) == len(amounts):
			self.ERROR("Array length mismatch with " + str(len(tokens)) + " tokens and " + str(len(amounts)) + " amounts.");
			return(False);
		numElements = len(tokens);
		sufficientBalance = True;
		for i in range(numElements):
			token = tokens[i];
			amount = amounts[i];
			currentHasSufficientBalance = self.erc20HasSufficientBalance(token, amount);
			sufficientBalance &= currentHasSufficientBalance;
		return(sufficientBalance);

	def erc20HasSufficientAllowance(self, tokenAddress, allowedAddress, amount):
		currentAllowance = self.erc20GetAllowanceStandard(tokenAddress, allowedAddress);
		balance = self.erc20GetBalanceStandard(tokenAddress);

		print("Token:", tokenAddress);
		print("\tCurrent Allowance:", currentAllowance);
		print("\tCurrent Balance:", balance);
		print("\tAmount to Spend:", amount);

		sufficient = (currentAllowance >= amount);

		if not sufficient:
			print("\tInsufficient allowance!");
			print("\tWill need to unlock", tokenAddress);
		else:
			print("\tWallet has sufficient allowance.");
		print();
		return(sufficient);

	def erc20EnforceSufficientAllowance(self,
										tokenAddress,
										allowedAddress,
										targetAllowance,
										amount,
										gasFactor,
										gasSpeed,
										nonceOverride,
										gasEstimateOverride,
										gasPriceGweiOverride,
										isAsync):
		if not self.erc20HasSufficientAllowance(tokenAddress, allowedAddress, amount):
			if targetAllowance == -1 or targetAllowance == self.INFINITE:
				targetAllowance = self.INFINITE;
			else:
				decimals = self.erc20GetDecimals(tokenAddress);
				targetAllowance = targetAllowance * 10**decimals;
			targetAllowance = int(targetAllowance);
			print("Insufficient Allowance. Increasing allowance to", targetAllowance);
			txHash = self.erc20SignAndSendNewAllowance(tokenAddress, allowedAddress, targetAllowance, gasFactor, gasSpeed, nonceOverride=nonceOverride, isAsync=isAsync);
			return(txHash);
		return(None);

	def erc20EnforceSufficientVaultAllowance(self, tokenAddress, targetAllowance, amount, gasFactor, gasSpeed, nonceOverride=-1, gasEstimateOverride=-1, gasPriceGweiOverride=-1, isAsync=False):
		return(self.erc20EnforceSufficientAllowance(tokenAddress, self.VAULT, targetAllowance, amount, gasFactor, gasSpeed, nonceOverride, gasEstimateOverride, gasPriceGweiOverride, isAsync));

	def erc20GetTargetAllowancesFromPoolData(self, poolDescription):
		(tokens, checksumTokens) = self.balSortTokens(list(poolDescription["tokens"].keys()));
		allowances = [];
		for token in tokens:
			targetAllowance = -1;
			if "allowance" in poolDescription["tokens"][token].keys():
				targetAllowance = poolDescription["tokens"][token]["allowance"];
			if targetAllowance == -1:
				targetAllowance = self.INFINITE;
			allowances.append(targetAllowance);
		return(tokens, allowances);

	def erc20AsyncEnforceSufficientVaultAllowances(self, tokens, targetAllowances, amounts, gasFactor, gasSpeed, nonceOverride=-1, gasEstimateOverride=-1, gasPriceGweiOverride=-1):
		if not len(tokens) == len(targetAllowances):
			self.ERROR("Array length mismatch with " + str(len(tokens)) + " tokens and " + str(len(targetAllowances)) + " targetAllowances.");
			return(False);

		nonce = self.web3.eth.get_transaction_count(self.web3.eth.default_account);
		txHashes = [];
		numElements = len(tokens);
		for i in range(numElements):
			token = tokens[i];
			targetAllowance = targetAllowances[i];
			amount = amounts[i];
			txHash = self.erc20EnforceSufficientVaultAllowance(token, targetAllowance, amount, gasFactor, gasSpeed, nonceOverride=nonce, isAsync=True);
			if not txHash is None:
				txHashes.append(txHash);
				nonce += 1;
		
		for txHash in txHashes:
			self.waitForTx(txHash)
		return(True)

	# =====================
	# ====Etherscan Gas====
	# =====================
	def getGasPriceEtherscanGwei(self, speed):
		dt = (time.time() - self.lastEtherscanCallTime);
		if dt < 1.0/self.etherscanMaxRate:
			time.sleep((1.0/self.etherscanMaxRate - dt) * 1.1);

		if not speed in self.etherscanSpeedDict.keys():
			print("[ERROR] Speed entered is:", speed);
			print("\tSpeed must be 'slow', 'average', or 'fast'");
			return(False);

		response = requests.get("https://api.etherscan.io/api?module=gastracker&action=gasoracle&apikey=" + self.etherscanApiKey);
		self.lastEtherscanCallTime = time.time();
		return(response.json()["result"][self.etherscanSpeedDict[speed]]);

	def balSortTokens(self, tokensIn):
		tokensIn.sort();
		checksumTokens = [self.web3.toChecksumAddress(t) for t in tokensIn];
		return(tokensIn, checksumTokens);

	def balWeightsEqualOne(self, poolData):
		tokenData = poolData["tokens"];
		tokens = tokenData.keys();
		
		weightSum = 0.0;
		for token in tokens:
			weightSum += tokenData[token]["weight"];
		
		weightEqualsOne = (weightSum == 1.0)
		if not weightEqualsOne:
			self.ERROR("Token weights add up to " + str(weightSum) + ", but they must add up to 1.0");
		return(weightEqualsOne);

	def balConvertTokensToWei(self, tokens, amounts):
		rawTokens = [];
		if not len(tokens) == len(amounts):
			self.ERROR("Array length mismatch with " + str(len(tokens)) + " tokens and " + str(len(amounts)) + " amounts.");
			return(False);
		numElements = len(tokens);
		for i in range(numElements):
			token = tokens[i];
			rawValue = amounts[i];
			decimals = self.erc20GetDecimals(token);
			raw = int(rawValue * 10**decimals);
			rawTokens.append(raw);
		return(rawTokens);

	def balGetFactoryContract(self, poolFactoryName):
		address = self.contractAddresses[poolFactoryName];
		abi = self.abis[poolFactoryName];
		factory = self.web3.eth.contract(address=address, abi=abi);
		return(factory);

	def balSetOwner(self, poolData):
		owner = self.ZERO_ADDRESS;
		if "owner" in poolData.keys():
			ownerAddress = poolData["owner"];
			if not len(ownerAddress) == 42:
				self.ERROR("Entry for \"owner\" must be a 42 character Ethereum address beginning with \"0x\"");
				return(False);
			owner = self.web3.toChecksumAddress(ownerAddress);
		return(owner);

	def balCreateFnWeightedPoolFactory(self, poolData):
		factory = self.balGetFactoryContract("WeightedPoolFactory");
		(tokens, checksumTokens) = self.balSortTokens(list(poolData["tokens"].keys()));
		intWithDecimalsWeights = [int(poolData["tokens"][t]["weight"] * 1e18) for t in tokens];
		swapFeePercentage = int(poolData["swapFeePercent"] * 1e16);

		if not self.balWeightsEqualOne(poolData):
			return(False);

		owner = self.balSetOwner(poolData);

		createFunction = factory.functions.create(	poolData["name"], 
													poolData["symbol"], 
													checksumTokens, 
													intWithDecimalsWeights, 
													swapFeePercentage, 
													owner);
		return(createFunction);

	def balCreateFnWeightedPool2TokensFactory(self, poolData):
		factory = self.balGetFactoryContract("WeightedPool2TokensFactory");
		(tokens, checksumTokens) = self.balSortTokens(list(poolData["tokens"].keys()));
		
		if not len(tokens) == 2:
			self.ERROR("WeightedPool2TokensFactory requires 2 tokens, but", len(tokens), "were given.");
			return(False);

		if not self.balWeightsEqualOne(poolData):
			return(False);

		intWithDecimalsWeights = [int(poolData["tokens"][t]["weight"] * 1e18) for t in tokens];
		swapFeePercentage = int(poolData["swapFeePercent"] * 1e16);

		owner = self.balSetOwner(poolData);

		oracleEnabled = False;
		if "oracleEnabled" in poolData.keys():
			oracleEnabled = poolData["oracleEnabled"];
			if isinstance(oracleEnabled, str):
				if oracleEnabled.lower() == "true":
					oracleEnabled = True;
				else:
					oracleEnabled = False;

		createFunction = factory.functions.create(	poolData["name"],
													poolData["symbol"],
													checksumTokens,
													intWithDecimalsWeights,
													swapFeePercentage,
													oracleEnabled,
													owner);
		return(createFunction);

	def balCreateFnStablePoolFactory(self, poolData):
		factory = self.balGetFactoryContract("StablePoolFactory");
		(tokens, checksumTokens) = self.balSortTokens(list(poolData["tokens"].keys()));
		swapFeePercentage = int(poolData["swapFeePercent"] * 1e16);

		owner = self.balSetOwner(poolData);

		createFunction = factory.functions.create(	poolData["name"],
													poolData["symbol"],
													checksumTokens,
													poolData["amplificationParameter"],
													swapFeePercentage,
													owner);
		return(createFunction);

	def balCreatePoolInFactory(self, poolDescription, gasFactor, gasPriceSpeed, nonceOverride=-1, gasEstimateOverride=-1, gasPriceGweiOverride=-1):
		createFunction = None;
		poolFactoryName = poolDescription["poolType"] + "Factory";

		# list of all supported pool factories
		# NOTE: when you add a pool factory to this list, be sure to
		# 		add it to the printout of supported factories below
		if poolFactoryName == "WeightedPoolFactory":
			createFunction = self.balCreateFnWeightedPoolFactory(poolDescription);
		if poolFactoryName == "WeightedPool2TokensFactory":
			createFunction = self.balCreateFnWeightedPool2TokensFactory(poolDescription);
		if poolFactoryName == "StablePoolFactory":
			createFunction = self.balCreateFnStablePoolFactory(poolDescription);
		if createFunction is None:
			print("No pool factory found with name:", poolFactoryName);
			print("Currently supported pool types are:");
			print("\tWeightedPool");
			print("\tWeightedPool2Token");
			print("\tStablePool");
			return(False);

		print("Pool function created, generating transaction...");
		tx = self.buildTx(createFunction, gasFactor, gasPriceSpeed, nonceOverride, gasEstimateOverride, gasPriceGweiOverride);
		print("Transaction Generated!");
		txHash = self.sendTx(tx);
		return(txHash);

	def balGetPoolIdFromHash(self, txHash):
		receipt = self.getTxReceipt(txHash, delay=2, maxRetries=5);
		
		# PoolRegistered event lives in the Vault
		vault = self.web3.eth.contract(address=self.VAULT, abi=self.abis["Vault"]);
		logs = vault.events.PoolRegistered().processReceipt(receipt);
		poolId = logs[0]['args']['poolId'].hex();
		print("\nDon't worry about that ^ warning, everything's fine :)");
		print("Your pool ID is:");
		print("\t0x" + str(poolId));
		return(poolId);

	def balRegisterPoolWithVault(self, poolDescription, poolId, gasFactor=1.05, gasPriceSpeed="average", nonceOverride=-1, gasEstimateOverride=-1, gasPriceGweiOverride=-1):

		(sortedTokens, checksumTokens) = self.balSortTokens(list(poolDescription["tokens"].keys()));
		initialBalancesBySortedTokens = [poolDescription["tokens"][token]["initialBalance"] for token in sortedTokens];

		rawInitBalances = self.balConvertTokensToWei(sortedTokens, initialBalancesBySortedTokens);
		JOIN_KIND_INIT = 0;
		initUserDataEncoded = eth_abi.encode_abi(	['uint256', 'uint256[]'], 
													[JOIN_KIND_INIT, rawInitBalances]);
		(tokens, checksumTokens) = self.balSortTokens(list(poolDescription["tokens"].keys()));
		joinPoolRequestTuple = (checksumTokens, rawInitBalances, initUserDataEncoded.hex(), poolDescription["fromInternalBalance"]);
		vault = self.web3.eth.contract(address=self.VAULT, abi=self.abis["Vault"]);
		joinPoolFunction = vault.functions.joinPool(poolId, 
												self.web3.toChecksumAddress(self.web3.eth.default_account), 
												self.web3.toChecksumAddress(self.web3.eth.default_account), 
												joinPoolRequestTuple);
		tx = self.buildTx(joinPoolFunction, gasFactor, gasPriceSpeed, nonceOverride, gasEstimateOverride, gasPriceGweiOverride);
		print("Transaction Generated!");		
		txHash = self.sendTx(tx);
		return(txHash);

	def balVaultWeth(self):
		vault = self.web3.eth.contract(address=self.VAULT, abi=self.abis["Vault"]);
		wethAddress = vault.functions.WETH().call();
		return(wethAddress);

	def balSwapIsFlashSwap(self, swapDescription):
		for amount in swapDescription["limits"]:
			if not float(amount) == 0.0:
				return(False);
		return(True);

	def balReorderTokenDicts(self, tokens):
		originalIdxToSortedIdx = {};
		sortedIdxToOriginalIdx = {};
		tokenAddressToIdx = {};
		for i in range(len(tokens)):
			tokenAddressToIdx[tokens[i]] = i;
		sortedTokens = tokens;
		sortedTokens.sort();
		for i in range(len(sortedTokens)):
			originalIdxToSortedIdx[tokenAddressToIdx[sortedTokens[i]]] = i;
			sortedIdxToOriginalIdx[i] = tokenAddressToIdx[sortedTokens[i]];
		return(sortedTokens, originalIdxToSortedIdx, sortedIdxToOriginalIdx);

	def balSwapGetUserData(self, poolType):
		userDataNull = eth_abi.encode_abi(['uint256'], [0]);
		userData = userDataNull;
		#for weightedPools, user data is just null, but in the future there may be userData to pass to pools for swaps
		# if poolType == "someFuturePool":
		# 	userData = "something else";
		return(userData);

	def balDoBatchSwap(self, swapDescription, isAsync=False, gasFactor=1.05, gasPriceSpeed="average", nonceOverride=-1, gasEstimateOverride=-1, gasPriceGweiOverride=-1):
		batchSwapFn = self.balCreateFnBatchSwap(swapDescription);
		tx = self.buildTx(batchSwapFn, gasFactor, gasPriceSpeed, nonceOverride, gasEstimateOverride, gasPriceGweiOverride);
		txHash = self.sendTx(tx, isAsync);
		return(txHash);

	def balCreateFnBatchSwap(self, swapDescription):
		(sortedTokens, originalIdxToSortedIdx, sortedIdxToOriginalIdx) = self.balReorderTokenDicts(swapDescription["assets"]);
		numTokens = len(sortedTokens);

		# reorder the limits to refer to properly sorted tokens
		reorderedLimits = [];
		for i in range(numTokens):
			currLimitStandard = float(swapDescription["limits"][sortedIdxToOriginalIdx[i]]);
			decimals = self.erc20GetDecimals(sortedTokens[i]);
			currLimitRaw = int(currLimitStandard * 10**(decimals))
			reorderedLimits.append(currLimitRaw)

		kind = int(swapDescription["kind"]);
		assets = [self.web3.toChecksumAddress(token) for token in sortedTokens];

		swapsTuples = [];
		for swap in swapDescription["swaps"]:
			idxSortedIn = originalIdxToSortedIdx[int(swap["assetInIndex"])];
			idxSortedOut = originalIdxToSortedIdx[int(swap["assetOutIndex"])];
			decimals = self.erc20GetDecimals(sortedTokens[idxSortedIn]);
			amount = int( float(swap["amount"]) * 10**(decimals) );

			swapsTuple = (	swap["poolId"],
							idxSortedIn,
							idxSortedOut,
							amount,
							self.balSwapGetUserData(None));
			swapsTuples.append(swapsTuple);

		funds = (	self.web3.toChecksumAddress(swapDescription["funds"]["sender"]),
					swapDescription["funds"]["fromInternalBalance"],
					self.web3.toChecksumAddress(swapDescription["funds"]["recipient"]),
					swapDescription["funds"]["toInternalBalance"]);
		intReorderedLimits = [int(element) for element in reorderedLimits];
		deadline = int(swapDescription["deadline"]);
		vault = self.web3.eth.contract(address=self.VAULT, abi=self.abis["Vault"]);
		batchSwapFunction = vault.functions.batchSwap(	kind,
														swapsTuples,
														assets,
														funds,
														intReorderedLimits,
														deadline);
		return(batchSwapFunction);
