# Research library only; deliberately separate from the live readsb build.
CXX ?= c++
CXXFLAGS ?= -O3 -std=c++20 -ffast-math -fPIC
CPPFLAGS += -DSTATS_ENABLED=0 -DSTREAM1090_MIN_SNR=2.5 -DSTREAM1090_PREAMBLE_GATE=1 -DSTREAM1090_PREAMBLE_THRESHOLD=1.2
.PHONY: all clean
all: libstream1090-native.so
libstream1090-native.so: native.cpp native.h $(wildcard upstream/*.hpp)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) $(ARCHFLAGS) -c native.cpp -o native.o
	$(CXX) -shared native.o -o $@
clean:
	rm -f libstream1090-native.so native.o
