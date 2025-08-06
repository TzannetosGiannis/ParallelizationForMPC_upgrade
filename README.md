# MPC Compiler

## [Generated results page](https://github.com/AnonymousResearcherGh/mp_opa/blob/gh-pages/README.md)

## Setup instructions (Ubuntu)

1. Install Ubuntu dependencies
   ```sh
   sudo apt-get update
   sudo apt-get install graphviz python3 python3-pip
   ```

   MOTION dependencies:
   ```sh
   sudo apt-get install build-essential make git cmake libssl-dev libboost-program-options-dev
   ```

   MP-SPDZ dependencies:
   ```sh
   sudo apt-get install automake build-essential clang cmake git libboost-dev libboost-thread-dev libgmp-dev libntl-dev libsodium-dev libssl-dev libtool python3
2. Clone the repo (the `--recursive` is required for the backend submodules)
   ```sh
   git clone --recursive https://github.com/AnonymousResearcherGh/mp_opa.git
   ```
3. Go to the `compiler` directory
   ```sh
   cd mp_opa/compiler
   ```
4. Install Python dependencies
   ```sh
   pip install -r requirements.txt
   ```
   
## Run instructions

- `compiler/main.py` - Script for running the compiler and seeing text output for all the stages
- `compiler/run_tests.py` - Script for running the tests
- `compiler/make_results_markdown.py` - Script for generating the results page at https://github.com/AnonymousResearcherGh/mp_opa/blob/gh-pages/README.md
- `compiler/paper_benchmarks.py` - Script for executing lan mpc experiments for MOTION and MP-SPDZ in a 2PC setup (server-client)

## Running paper benchmarks
```sh

   cd mp_opa/backend_submodules/
   bash change_registy_boost.sh # update one discontinued dependency on MOTION
   cd ../
   python compiler/make_results_markdown.py static # runs the gh-pages code and stores result locally in folder static

   # DOES NOT RUN ON LOCALHOST!!
   # Run from server
   python paper_benchmarks.py -r s -a {SERVER_IP} -b MOTION # or MP-SPDZ
 
   # Run from client
   python paper_benchmarks.py -r c -a {SERVER_IP} -b MOTION # or MP-SPDZ
   ```