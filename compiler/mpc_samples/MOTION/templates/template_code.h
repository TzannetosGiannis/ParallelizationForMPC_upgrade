#pragma once

#include <algorithm>
#include <cassert>
#include <functional>
#include <vector>

#include "base/party.h"
#include "secure_type/secure_unsigned_integer.h"

// clang-format off
encrypto::motion::SecureUnsignedInteger  template_code(
    encrypto::motion::PartyPointer &party,
    encrypto::motion::SecureUnsignedInteger list_A,
    encrypto::motion::SecureUnsignedInteger list_B
    
) {
    
    encrypto::motion::SecureUnsignedInteger result_C;
    
    for (int i = 0; i < _iters; i++) {
        result_C = list_A _operator list_B;
    }

    std::vector<encrypto::motion::SecureUnsignedInteger> result_C_unsimdified = result_C.Unsimdify();

    encrypto::motion::SecureUnsignedInteger result = result_C_unsimdified[0];
    for (std::size_t i = 1; i < result_C_unsimdified.size(); i++) result += result_C_unsimdified[i];

    return result;

}
// clang-format on

// vim: set ft=cpp :

// Emacs:
// Local Variables:
// mode: cpp
// End: