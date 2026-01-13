# Overview

This project implements an HTTP REST API as an interface to build and run
machine learning models.  The REST API is implemented using Flask.  And the 
machine learning models are implemented using Nupic. 

Because, this project's goal is to run machine learning models with real-time 
time series data I used data from Bitmex's Test Net.

**NOTE**

When launched on its own, this Docker container will only bring up a REST API
interface, but will not instatiate nor run any machine learning models.  To
instantiate and run models you must make calls to the REST API.

# Building The Docker Container

Because, Docker Compose is used you can build the container by 
executing the following in a terminal.

```shell script
export VERSION=1.1 
VERSION=1.1 docker compose build && \
docker push registry.cybertron.ninja/nupic_predictor:${VERSION}
unset VERSION
```

# Deploying the Entire BAMM Stack on JONIN

There are three Docker stacks in the `BAMM` stack, which must be brought up 
in the following order:

1. nupic-predictor
    - **NOTE:** This stack provisions the Docker networks for the entire `BAMM` stack.
2. algo-backend
3. crypto-trading-gym

To deploy the Nupic Predictor REST API execute the following on a Docker
Swarm manager node.

## Nupic Predictor Stack

---

### Step 1: One-Time Setup 

Execute this step one time only in order to create the requied user accounts and also data directories.

```shell
addserviceuser 9000 bamm
mkdir -p /mnt/cn_data/bamm/nupic_models
chown -R bamm:bamm /mnt/cn_data/bamm/nupic_models
```

### Step 2: Launch Nupic Predictor REST API

```shell script
docker stack deploy -c stack.jonin.yaml bamm-nupic-predictor
```

Once launched the REST API should be available at http://localhost:5000.


## Algo-Backend Stack

---

Execute the instructions found in `~/Documents/Development_Projects/cybertron.ninja/algo-backend/README.md`

## Crypto Trading Gym Stack

---

Execute the instructions found in `~/Documents/Development_Projects/Algo_Trading_Projects/Nupic_Projects/crypto_trading_gym/README.md`






