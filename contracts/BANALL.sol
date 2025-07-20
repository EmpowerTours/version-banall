// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

interface IERC20 {
    function transfer(address to, uint256 amount) external returns (bool);
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
    function balanceOf(address account) external view returns (uint256);
}

contract BANALL {
    address public owner;
    IERC20 public toursToken;
    uint256 public constant ENTRY_FEE = 1 ether; // 1 MON
    uint256 public constant PROFILE_REWARD = 0.00001 ether; // 10 MON / 1M users
    uint256 public constant TOURS_REWARD = 1e18; // 1 $TOURS per ban
    uint256 public constant MAX_PLAYERS = 1000;
    uint256 public constant GAME_DURATION = 5 minutes;
    uint256 public constant LOBBY_WAIT = 5 seconds;

    struct Player {
        address wallet;
        string username;
        bool isBanned;
        bool isSpectator;
        uint256 farcasterFid;
    }

    mapping(address => Player) public players;
    mapping(address => bool) public hasProfile;
    mapping(uint256 => address) public farcasterFidToAddress;
    address[] public activePlayers;
    address public bastralPlayer;
    uint256 public gameStartTime;
    bool public isGameActive;
    uint256 public totalPot;
    address public lastWinner;

    event GameStarted(uint256 startTime);
    event PlayerBanned(address indexed banned, address indexed by, uint256 farcasterFid);
    event GameEnded(address indexed winner, uint256 monPot, uint256 toursReward);
    event ProfileCreated(address indexed user, string username, uint256 farcasterFid);
    event RewardDistributed(address indexed user, uint256 amount);

    constructor(address _toursToken) {
        owner = msg.sender;
        toursToken = IERC20(_toursToken);
        totalPot = 0;
        isGameActive = false;
    }

    function createProfile(string memory _username, uint256 _farcasterFid) public payable {
        require(!hasProfile[msg.sender], "Profile already exists");
        require(_farcasterFid == 0 || farcasterFidToAddress[_farcasterFid] == address(0), "Farcaster FID taken");
        require(msg.value >= PROFILE_REWARD, "Insufficient profile fee");
        require(bytes(_username).length > 0, "Username cannot be empty");

        players[msg.sender] = Player(msg.sender, _username, false, false, _farcasterFid);
        hasProfile[msg.sender] = true;
        if (_farcasterFid != 0) {
            farcasterFidToAddress[_farcasterFid] = msg.sender;
        }
        if (address(this).balance >= PROFILE_REWARD) {
            payable(msg.sender).transfer(PROFILE_REWARD);
            emit RewardDistributed(msg.sender, PROFILE_REWARD);
        }
        emit ProfileCreated(msg.sender, _username, _farcasterFid);
    }

    function joinGame() public payable {
        require(hasProfile[msg.sender], "Create profile first");
        require(!isGameActive, "Game already active");
        require(msg.value == ENTRY_FEE, "Send exactly 1 MON");
        require(activePlayers.length < MAX_PLAYERS, "Game full");
        require(!players[msg.sender].isBanned, "Banned players cannot join");

        players[msg.sender].isSpectator = false;
        activePlayers.push(msg.sender);
        totalPot += msg.value;
    }

    function startGame(address _bastral) public {
        require(msg.sender == owner || msg.sender == lastWinner, "Only owner or last winner can start");
        require(activePlayers.length > 1, "Need at least 2 players");
        require(!isGameActive, "Game already active");

        if (_bastral != address(0)) {
            bool isValidPlayer = false;
            for (uint256 i = 0; i < activePlayers.length; i++) {
                if (activePlayers[i] == _bastral && !players[_bastral].isBanned) {
                    isValidPlayer = true;
                    break;
                }
            }
            require(isValidPlayer, "Invalid Bastral player");
            bastralPlayer = _bastral;
        } else {
            uint256 randomIndex = uint256(keccak256(abi.encodePacked(block.timestamp, block.prevrandao))) % activePlayers.length;
            bastralPlayer = activePlayers[randomIndex];
        }

        isGameActive = true;
        gameStartTime = block.timestamp;
        emit GameStarted(gameStartTime);
    }

    function banBastral() public {
        require(isGameActive, "Game not active");
        require(block.timestamp < gameStartTime + GAME_DURATION, "Game ended");
        require(msg.sender != bastralPlayer, "Cannot ban yourself");
        require(!players[msg.sender].isBanned, "Banned players cannot ban");
        require(players[bastralPlayer].wallet == bastralPlayer, "Bastral already banned");

        players[bastralPlayer].isBanned = true;
        require(toursToken.transfer(msg.sender, TOURS_REWARD), "TOURS reward transfer failed");
        emit PlayerBanned(bastralPlayer, msg.sender, players[msg.sender].farcasterFid);

        // Select new Bastral
        address newBastral = address(0);
        for (uint256 i = 0; i < activePlayers.length; i++) {
            if (!players[activePlayers[i]].isBanned) {
                newBastral = activePlayers[i];
                break;
            }
        }
        bastralPlayer = newBastral;

        // Check for winner
        uint256 unbannedCount = 0;
        address winner = address(0);
        for (uint256 i = 0; i < activePlayers.length; i++) {
            if (!players[activePlayers[i]].isBanned) {
                unbannedCount++;
                winner = activePlayers[i];
            }
        }
        if (unbannedCount <= 1) {
            isGameActive = false;
            if (unbannedCount == 1) {
                lastWinner = winner;
                uint256 toursWinReward = totalPot * 2;
                require(toursToken.transfer(winner, toursWinReward), "Winner TOURS transfer failed");
                payable(winner).transfer(totalPot);
                emit GameEnded(winner, totalPot, toursWinReward);
            }
            totalPot = 0;
            for (uint256 i = 0; i < activePlayers.length; i++) {
                players[activePlayers[i]].isBanned = false;
            }
            delete activePlayers;
        }
    }

    function addSpectator() public {
        require(hasProfile[msg.sender], "Create profile first");
        require(!isGameActive || !players[msg.sender].isBanned, "Cannot spectate if banned");
        players[msg.sender].isSpectator = true;
    }

    function getGameState() public view returns (uint256 timeLeft, address bastral, address[] memory playersList, string[] memory usernames, bool[] memory banned, uint256[] memory toursBalances, bool[] memory spectators, uint256[] memory farcasterFids) {
        timeLeft = isGameActive ? (gameStartTime + GAME_DURATION > block.timestamp ? gameStartTime + GAME_DURATION - block.timestamp : 0) : 0;
        playersList = activePlayers;
        usernames = new string[](activePlayers.length);
        banned = new bool[](activePlayers.length);
        toursBalances = new uint256[](activePlayers.length);
        spectators = new bool[](activePlayers.length);
        farcasterFids = new uint256[](activePlayers.length);
        for (uint256 i = 0; i < activePlayers.length; i++) {
            usernames[i] = players[activePlayers[i]].username;
            banned[i] = players[activePlayers[i]].isBanned;
            toursBalances[i] = toursToken.balanceOf(activePlayers[i]);
            spectators[i] = players[activePlayers[i]].isSpectator;
            farcasterFids[i] = players[activePlayers[i]].farcasterFid;
        }
        return (timeLeft, bastralPlayer, playersList, usernames, banned, toursBalances, spectators, farcasterFids);
    }

    function depositTours(uint256 amount) public {
        require(toursToken.transferFrom(msg.sender, address(this), amount), "Transfer failed");
    }

    receive() external payable {}
}
