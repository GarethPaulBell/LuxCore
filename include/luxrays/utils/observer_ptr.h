/***************************************************************************
 * Copyright 1998-2026 by authors (see AUTHORS.txt)                        *
 *                                                                         *
 *   This file is part of LuxCoreRender.                                   *
 *                                                                         *
 * Licensed under the Apache License, Version 2.0 (the "License");         *
 * you may not use this file except in compliance with the License.        *
 * You may obtain a copy of the License at                                 *
 *                                                                         *
 *     http://www.apache.org/licenses/LICENSE-2.0                          *
 *                                                                         *
 * Unless required by applicable law or agreed to in writing, software     *
 * distributed under the License is distributed on an "AS IS" BASIS,       *
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.*
 * See the License for the specific language governing permissions and     *
 * limitations under the License.                                          *
 ***************************************************************************/
// vim: autoindent noexpandtab tabstop=4 shiftwidth=4

#include <cstddef>	// for nullptr_t
#include <utility>	// for std::swap
#include <boost/serialization/split_free.hpp>
#include <boost/serialization/nvp.hpp>

namespace luxrays {

template <typename T>
class observer_ptr {
public:
      using element_type = std::remove_extent_t<T>;

	// Default constructor: initialize to nullptr
	constexpr observer_ptr() noexcept : ptr(nullptr) {}
	constexpr observer_ptr(std::nullptr_t) noexcept : ptr(nullptr) {}

	// Constructor from raw pointer (implicit conversions allowed)
	constexpr observer_ptr(T* p) noexcept : ptr(p) {}

	// Copy constructor and assignment
	constexpr observer_ptr(const observer_ptr&) noexcept = default;
	constexpr observer_ptr& operator=(const observer_ptr&) noexcept = default;

	// Move constructor and assignment
	constexpr observer_ptr(observer_ptr&&) noexcept = default;
	constexpr observer_ptr& operator=(observer_ptr&&) noexcept = default;

	// Assignment from raw pointer
	constexpr observer_ptr& operator=(T* p) noexcept {
		ptr = p;
		return *this;
	}

        // Conversion to pointer
        constexpr operator T*() { return ptr; }
        constexpr operator const T*() const { return ptr; }

	// Destructor
	~observer_ptr() = default;

	// Dereference operators
	constexpr T& operator*() const noexcept { return *ptr; }
	constexpr T* operator->() const noexcept { return ptr; }

	// Conversion to bool (for boolean context)
	explicit constexpr operator bool() const noexcept { return ptr != nullptr; }

	// Get the raw pointer
	constexpr T* get() const noexcept { return ptr; }

	// Reset to nullptr
	constexpr void reset() noexcept { ptr = nullptr; }

	// Swap with another observer_ptr
	void swap(observer_ptr& other) noexcept { std::swap(ptr, other.ptr); }

	// Comparison operators
	friend constexpr bool operator==(const observer_ptr& lhs, const observer_ptr& rhs) noexcept {
		return lhs.ptr == rhs.ptr;
	}
	friend constexpr bool operator!=(const observer_ptr& lhs, const observer_ptr& rhs) noexcept {
		return lhs.ptr != rhs.ptr;
	}
	friend constexpr bool operator==(const observer_ptr& lhs, std::nullptr_t) noexcept {
		return lhs.ptr == nullptr;
	}
	friend constexpr bool operator!=(const observer_ptr& lhs, std::nullptr_t) noexcept {
		return lhs.ptr != nullptr;
	}

	// Comparison with raw pointers (const T*)
	friend constexpr bool operator==(const observer_ptr& lhs, const T* rhs) noexcept {
		return lhs.ptr == rhs;
	}
	friend constexpr bool operator!=(const observer_ptr& lhs, const T* rhs) noexcept {
		return lhs.ptr != rhs;
	}
	friend constexpr bool operator==(const T* lhs, const observer_ptr& rhs) noexcept {
		return lhs == rhs.ptr;
	}
	friend constexpr bool operator!=(const T* lhs, const observer_ptr& rhs) noexcept {
		return lhs != rhs.ptr;
	}

        // Converting constructor from observer_ptr<U> to observer_ptr<T>
        template <typename U, typename = std::enable_if_t<std::is_convertible_v<U*, T*>>>
        constexpr observer_ptr(const observer_ptr<U>& other) noexcept : ptr(other.get()) {}

        // Converting assignment operator from observer_ptr<U> to observer_ptr<T>
        template <typename U, typename = std::enable_if_t<std::is_convertible_v<U*, T*>>>
        constexpr observer_ptr& operator=(const observer_ptr<U>& other) noexcept {
            ptr = other.get();
            return *this;
        }


	// Boost.Serialization support
	template <typename Archive>
	void serialize(Archive& ar, const unsigned int /* version */) {
		ar & boost::serialization::make_nvp("ptr", ptr);
	}

private:
	T* ptr;
};


// Free function for dynamic casting observer_ptr<B> to observer_ptr<A>
template<class T, class U>
observer_ptr<T> dynamic_observer_cast(const observer_ptr<U>& r) noexcept
{
    if (auto p = dynamic_cast<typename observer_ptr<T>::element_type*>(r.get()))
        return observer_ptr<T>(r);
    else
        return observer_ptr<T>{nullptr};
}

template<class T, class U>
observer_ptr<const T> dynamic_observer_cast(const observer_ptr<const U>& r) noexcept
{
    if (auto p = dynamic_cast<const typename observer_ptr<const T>::element_type*>(r.get()))
        return observer_ptr<const T>(p);
    else
        return observer_ptr<const T>{nullptr};
}
//template<class T, class U>
//observer_ptr<T> dynamic_observer_cast( observer_ptr<U> && r ) noexcept
//{
    //(void) dynamic_cast< T* >( static_cast< U* >( 0 ) );

    //typedef typename observer_ptr<T>::element_type E;

    //E * p = dynamic_cast< E* >( r.get() );
    //return p? observer_ptr<T>( std::move(r) ): observer_ptr<T>();
//}

template<class T, class U>
observer_ptr<T> static_observer_cast(const observer_ptr<U>& r) noexcept
{
    if (auto p = static_cast<typename observer_ptr<T>::element_type*>(r.get()))
        return observer_ptr<T>(r);
    else
        return observer_ptr<T>{nullptr};
}

template<class T, class U>
observer_ptr<const T> static_observer_cast(const observer_ptr<const U>& r) noexcept
{
    if (auto p = static_cast<const typename observer_ptr<const T>::element_type*>(r.get()))
        return observer_ptr<const T>(p);
    else
        return observer_ptr<const T>{nullptr};
}

// Non-member swap
template <typename T>
void swap(observer_ptr<T>& lhs, observer_ptr<T>& rhs) noexcept {
	lhs.swap(rhs);
}

} // namespace luxrays

// Boost.Serialization split free function for non-intrusive serialization
namespace boost {
namespace serialization {

template <typename Archive, typename T>
void save(Archive& ar, const luxrays::observer_ptr<T>& ptr, const unsigned int /* version */) {
	T* raw_ptr = ptr.get();
	ar << boost::serialization::make_nvp("ptr", raw_ptr);
}

template <typename Archive, typename T>
void load(Archive& ar, luxrays::observer_ptr<T>& ptr, const unsigned int /* version */) {
	T* raw_ptr;
	ar >> boost::serialization::make_nvp("ptr", raw_ptr);
	ptr = raw_ptr;
}

template <typename Archive, typename T>
void serialize(Archive& ar, luxrays::observer_ptr<T>& ptr, const unsigned int version) {
	boost::serialization::split_free(ar, ptr, version);
}

} // namespace serialization
} // namespace boost
