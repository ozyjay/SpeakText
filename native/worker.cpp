#include "whisper.h"

#include <algorithm>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <limits>
#include <memory>
#include <string>
#include <thread>
#include <vector>

namespace {

constexpr std::uint32_t kBytesPerSample = 2;
// The coordinator stops at 120 seconds; allow a small PipeWire shutdown tail.
constexpr std::uint32_t kMaximumPcmBytes = 16000U * kBytesPerSample * 125U;

struct WhisperContextDeleter {
    void operator()(whisper_context* context) const noexcept {
        whisper_free(context);
    }
};

using WhisperContext = std::unique_ptr<whisper_context, WhisperContextDeleter>;

bool read_exact(std::istream& input, char* destination, std::size_t length) {
    input.read(destination, static_cast<std::streamsize>(length));
    return input.good() || input.gcount() == static_cast<std::streamsize>(length);
}

bool read_u32(std::istream& input, std::uint32_t& value) {
    unsigned char encoded[4]{};
    if (!read_exact(input, reinterpret_cast<char*>(encoded), sizeof(encoded))) {
        return false;
    }
    value = static_cast<std::uint32_t>(encoded[0]) |
            (static_cast<std::uint32_t>(encoded[1]) << 8U) |
            (static_cast<std::uint32_t>(encoded[2]) << 16U) |
            (static_cast<std::uint32_t>(encoded[3]) << 24U);
    return true;
}

void write_u32(std::ostream& output, std::uint32_t value) {
    const unsigned char encoded[4] = {
        static_cast<unsigned char>(value & 0xffU),
        static_cast<unsigned char>((value >> 8U) & 0xffU),
        static_cast<unsigned char>((value >> 16U) & 0xffU),
        static_cast<unsigned char>((value >> 24U) & 0xffU),
    };
    output.write(reinterpret_cast<const char*>(encoded), sizeof(encoded));
}

std::vector<float> decode_pcm(const std::vector<char>& bytes) {
    std::vector<float> samples(bytes.size() / kBytesPerSample);
    for (std::size_t index = 0; index < samples.size(); ++index) {
        const auto low = static_cast<unsigned char>(bytes[index * 2]);
        const auto high = static_cast<unsigned char>(bytes[index * 2 + 1]);
        const auto encoded = static_cast<std::uint16_t>(low) |
                             (static_cast<std::uint16_t>(high) << 8U);
        std::int16_t sample{};
        std::memcpy(&sample, &encoded, sizeof(sample));
        samples[index] = static_cast<float>(sample) / 32768.0F;
    }
    return samples;
}

std::string transcribe(whisper_context* context, const std::vector<float>& samples) {
    whisper_full_params parameters =
        whisper_full_default_params(WHISPER_SAMPLING_GREEDY);
    parameters.n_threads = static_cast<int>(std::clamp(
        std::thread::hardware_concurrency(), 1U, 8U));
    parameters.language = "en";
    parameters.translate = false;
    parameters.no_timestamps = true;
    parameters.print_progress = false;
    parameters.print_realtime = false;
    parameters.print_timestamps = false;
    parameters.print_special = false;

    if (whisper_full(
            context,
            parameters,
            samples.data(),
            static_cast<int>(samples.size())) != 0) {
        throw std::runtime_error("whisper_full failed");
    }

    std::string transcript;
    const int segment_count = whisper_full_n_segments(context);
    for (int segment = 0; segment < segment_count; ++segment) {
        const char* text = whisper_full_get_segment_text(context, segment);
        if (text != nullptr) {
            transcript.append(text);
        }
    }
    return transcript;
}

}  // namespace

int main(int argc, char** argv) {
    if (argc != 2) {
        std::cerr << "usage: speaktext-worker MODEL_PATH\n";
        return 2;
    }

    whisper_context_params context_parameters = whisper_context_default_params();
    context_parameters.use_gpu = false;
    WhisperContext context(
        whisper_init_from_file_with_params(argv[1], context_parameters));
    if (!context) {
        std::cerr << "could not load Whisper model\n";
        return 3;
    }

    std::cout << "READY\n" << std::flush;
    while (true) {
        std::uint32_t pcm_size = 0;
        if (!read_u32(std::cin, pcm_size)) {
            break;
        }
        if (pcm_size == 0) {
            return 0;
        }
        if (pcm_size > kMaximumPcmBytes || pcm_size % kBytesPerSample != 0) {
            std::cerr << "invalid PCM frame\n";
            return 4;
        }

        std::vector<char> pcm(pcm_size);
        if (!read_exact(std::cin, pcm.data(), pcm.size())) {
            std::cerr << "incomplete PCM frame\n";
            return 5;
        }

        try {
            const std::vector<float> samples = decode_pcm(pcm);
            const std::string transcript = transcribe(context.get(), samples);
            if (transcript.size() > std::numeric_limits<std::uint32_t>::max()) {
                throw std::runtime_error("transcript is too large");
            }
            write_u32(std::cout, static_cast<std::uint32_t>(transcript.size()));
            std::cout.write(
                transcript.data(), static_cast<std::streamsize>(transcript.size()));
            std::cout.flush();
        } catch (const std::exception& error) {
            std::cerr << "transcription failed: " << error.what() << '\n';
            return 6;
        }
    }
    return 0;
}
